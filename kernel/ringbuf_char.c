// SPDX-License-Identifier: GPL-2.0-only
#include <linux/atomic.h>
#include <linux/cdev.h>
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/fs.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/poll.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/version.h>
#include <linux/wait.h>

#include <ringbuf_char_ioctl.h>

#include "ringbuf_char_buffer.h"

struct ringbuf_char_dev {
	dev_t devt;
	struct cdev cdev;
	struct class *class;
	struct device *device;
	struct ringbuf_char_buffer buffer;
	struct mutex lock;
	wait_queue_head_t read_queue;
	wait_queue_head_t write_queue;
	atomic64_t state_generation;
	atomic64_t total_bytes_read;
	atomic64_t total_bytes_written;
	atomic64_t read_calls;
	atomic64_t write_calls;
	atomic64_t open_calls;
	atomic64_t open_handles;
	atomic64_t ioctl_calls;
	atomic64_t failed_operations;
	atomic64_t blocked_reads;
	atomic64_t blocked_writes;
	atomic64_t clears;
	atomic64_t resizes;
	u32 mode;
	bool shutting_down;
};

static unsigned int buffer_capacity = RINGBUF_CHAR_DEFAULT_CAPACITY;
module_param(buffer_capacity, uint, 0444);
MODULE_PARM_DESC(buffer_capacity,
		 "Initial circular-buffer capacity in bytes (256..65536)");

static bool debug;
module_param(debug, bool, 0644);
MODULE_PARM_DESC(debug, "Enable optional debug logging");

static struct ringbuf_char_dev *ringbuf_dev;

static bool ringbuf_char_capacity_valid_u64(u64 capacity)
{
	return capacity >= RINGBUF_CHAR_MIN_CAPACITY &&
	       capacity <= RINGBUF_CHAR_MAX_CAPACITY;
}

static bool ringbuf_char_nonblocking(const struct file *file,
				    const struct ringbuf_char_dev *dev)
{
	return (file->f_flags & O_NONBLOCK) ||
	       (READ_ONCE(dev->mode) & RINGBUF_CHAR_MODE_F_NONBLOCK);
}

static bool ringbuf_char_read_condition(struct ringbuf_char_dev *dev,
				       s64 seen_generation)
{
	return READ_ONCE(dev->shutting_down) ||
	       READ_ONCE(dev->buffer.len) > 0 ||
	       atomic64_read(&dev->state_generation) != seen_generation;
}

static bool ringbuf_char_write_condition(struct ringbuf_char_dev *dev,
					s64 seen_generation)
{
	size_t capacity = READ_ONCE(dev->buffer.capacity);
	size_t stored = READ_ONCE(dev->buffer.len);

	return READ_ONCE(dev->shutting_down) ||
	       capacity > stored ||
	       atomic64_read(&dev->state_generation) != seen_generation;
}

static void ringbuf_char_note_failure(struct ringbuf_char_dev *dev)
{
	atomic64_inc(&dev->failed_operations);
}

static void ringbuf_char_reset_stats(struct ringbuf_char_dev *dev)
{
	atomic64_set(&dev->total_bytes_read, 0);
	atomic64_set(&dev->total_bytes_written, 0);
	atomic64_set(&dev->read_calls, 0);
	atomic64_set(&dev->write_calls, 0);
	atomic64_set(&dev->open_calls, 0);
	atomic64_set(&dev->ioctl_calls, 0);
	atomic64_set(&dev->failed_operations, 0);
	atomic64_set(&dev->blocked_reads, 0);
	atomic64_set(&dev->blocked_writes, 0);
	atomic64_set(&dev->clears, 0);
	atomic64_set(&dev->resizes, 0);
}

static void ringbuf_char_fill_stats_locked(struct ringbuf_char_dev *dev,
					  struct ringbuf_char_stats *stats)
{
	memset(stats, 0, sizeof(*stats));
	stats->abi_version = RINGBUF_CHAR_ABI_VERSION;
	stats->struct_size = sizeof(*stats);
	stats->current_capacity = dev->buffer.capacity;
	stats->stored_bytes = ringbuf_char_buffer_stored(&dev->buffer);
	stats->available_bytes = ringbuf_char_buffer_available(&dev->buffer);
	stats->total_bytes_read = atomic64_read(&dev->total_bytes_read);
	stats->total_bytes_written = atomic64_read(&dev->total_bytes_written);
	stats->read_calls = atomic64_read(&dev->read_calls);
	stats->write_calls = atomic64_read(&dev->write_calls);
	stats->open_calls = atomic64_read(&dev->open_calls);
	stats->current_open_handles = atomic64_read(&dev->open_handles);
	stats->ioctl_calls = atomic64_read(&dev->ioctl_calls);
	stats->failed_operations = atomic64_read(&dev->failed_operations);
	stats->blocked_reads = atomic64_read(&dev->blocked_reads);
	stats->blocked_writes = atomic64_read(&dev->blocked_writes);
	stats->clears = atomic64_read(&dev->clears);
	stats->resizes = atomic64_read(&dev->resizes);
	stats->mode = dev->mode;
}

static int ringbuf_char_open(struct inode *inode, struct file *file)
{
	struct ringbuf_char_dev *dev;

	dev = container_of(inode->i_cdev, struct ringbuf_char_dev, cdev);
	file->private_data = dev;
	atomic64_inc(&dev->open_calls);
	atomic64_inc(&dev->open_handles);

	if (debug)
		pr_debug("ringbuf_char: opened, handles=%lld\n",
			 (long long)atomic64_read(&dev->open_handles));

	return 0;
}

static int ringbuf_char_release(struct inode *inode, struct file *file)
{
	struct ringbuf_char_dev *dev = file->private_data;

	(void)inode;
	if (dev)
		atomic64_dec(&dev->open_handles);

	return 0;
}

static ssize_t ringbuf_char_read(struct file *file, char __user *user_buffer,
				size_t count, loff_t *ppos)
{
	struct ringbuf_char_dev *dev = file->private_data;
	size_t copied = 0;
	int ret;

	(void)ppos;
	atomic64_inc(&dev->read_calls);

	if (count == 0)
		return 0;

	for (;;) {
		s64 seen_generation;

		ret = mutex_lock_interruptible(&dev->lock);
		if (ret) {
			ringbuf_char_note_failure(dev);
			return -ERESTARTSYS;
		}

		if (ringbuf_char_buffer_stored(&dev->buffer) > 0 ||
		    dev->shutting_down)
			break;

		if (ringbuf_char_nonblocking(file, dev)) {
			mutex_unlock(&dev->lock);
			ringbuf_char_note_failure(dev);
			return -EAGAIN;
		}

		seen_generation = atomic64_read(&dev->state_generation);
		atomic64_inc(&dev->blocked_reads);
		mutex_unlock(&dev->lock);

		ret = wait_event_interruptible(
			dev->read_queue,
			ringbuf_char_read_condition(dev, seen_generation));
		if (ret) {
			ringbuf_char_note_failure(dev);
			return -ERESTARTSYS;
		}

		ret = mutex_lock_interruptible(&dev->lock);
		if (ret) {
			ringbuf_char_note_failure(dev);
			return -ERESTARTSYS;
		}

		if (ringbuf_char_buffer_stored(&dev->buffer) == 0 &&
		    !dev->shutting_down &&
		    atomic64_read(&dev->state_generation) != seen_generation) {
			mutex_unlock(&dev->lock);
			return 0;
		}

		mutex_unlock(&dev->lock);
	}

	if (dev->shutting_down &&
	    ringbuf_char_buffer_stored(&dev->buffer) == 0) {
		mutex_unlock(&dev->lock);
		return 0;
	}

	while (copied < count && ringbuf_char_buffer_stored(&dev->buffer) > 0) {
		const u8 *src;
		size_t span = ringbuf_char_buffer_read_span(&dev->buffer, &src);
		size_t chunk = min(count - copied, span);

		if (copy_to_user(user_buffer + copied, src, chunk)) {
			ringbuf_char_note_failure(dev);
			pr_warn_ratelimited(
				"ringbuf_char: copy_to_user failed in read\n");
			if (copied == 0) {
				mutex_unlock(&dev->lock);
				return -EFAULT;
			}
			break;
		}

		ringbuf_char_buffer_consume(&dev->buffer, chunk);
		copied += chunk;
	}

	mutex_unlock(&dev->lock);

	if (copied > 0) {
		atomic64_add(copied, &dev->total_bytes_read);
		wake_up_interruptible(&dev->write_queue);
	}

	return copied;
}

static ssize_t ringbuf_char_write(struct file *file,
				 const char __user *user_buffer, size_t count,
				 loff_t *ppos)
{
	struct ringbuf_char_dev *dev = file->private_data;
	size_t copied = 0;
	size_t writable;
	int ret;

	(void)ppos;
	atomic64_inc(&dev->write_calls);

	if (count == 0)
		return 0;

	for (;;) {
		s64 seen_generation;

		ret = mutex_lock_interruptible(&dev->lock);
		if (ret) {
			ringbuf_char_note_failure(dev);
			return -ERESTARTSYS;
		}

		writable = ringbuf_char_buffer_available(&dev->buffer);
		if (writable > 0 || dev->shutting_down)
			break;

		if (ringbuf_char_nonblocking(file, dev)) {
			mutex_unlock(&dev->lock);
			ringbuf_char_note_failure(dev);
			return -EAGAIN;
		}

		seen_generation = atomic64_read(&dev->state_generation);
		atomic64_inc(&dev->blocked_writes);
		mutex_unlock(&dev->lock);

		ret = wait_event_interruptible(
			dev->write_queue,
			ringbuf_char_write_condition(dev, seen_generation));
		if (ret) {
			ringbuf_char_note_failure(dev);
			return -ERESTARTSYS;
		}
	}

	if (dev->shutting_down) {
		mutex_unlock(&dev->lock);
		ringbuf_char_note_failure(dev);
		return -ENODEV;
	}

	writable = min(count, writable);
	while (copied < writable) {
		u8 *dst;
		size_t span = ringbuf_char_buffer_write_span(&dev->buffer, &dst);
		size_t chunk = min(writable - copied, span);

		if (chunk == 0)
			break;

		if (copy_from_user(dst, user_buffer + copied, chunk)) {
			ringbuf_char_note_failure(dev);
			pr_warn_ratelimited(
				"ringbuf_char: copy_from_user failed in write\n");
			if (copied == 0) {
				mutex_unlock(&dev->lock);
				return -EFAULT;
			}
			break;
		}

		ringbuf_char_buffer_commit(&dev->buffer, chunk);
		copied += chunk;
	}

	mutex_unlock(&dev->lock);

	if (copied > 0) {
		atomic64_add(copied, &dev->total_bytes_written);
		wake_up_interruptible(&dev->read_queue);
	}

	return copied;
}

static long ringbuf_char_ioctl(struct file *file, unsigned int cmd,
			      unsigned long arg)
{
	struct ringbuf_char_dev *dev = file->private_data;
	int ret = 0;

	atomic64_inc(&dev->ioctl_calls);

	if (_IOC_TYPE(cmd) != RINGBUF_CHAR_IOC_MAGIC ||
	    _IOC_NR(cmd) > RINGBUF_CHAR_IOC_MAXNR) {
		ringbuf_char_note_failure(dev);
		pr_warn_ratelimited("ringbuf_char: unsupported ioctl 0x%x\n",
				    cmd);
		return -ENOTTY;
	}

	switch (cmd) {
	case RINGBUF_CHAR_IOC_CLEAR:
		mutex_lock(&dev->lock);
		ringbuf_char_buffer_clear(&dev->buffer);
		atomic64_inc(&dev->clears);
		atomic64_inc(&dev->state_generation);
		mutex_unlock(&dev->lock);
		wake_up_interruptible_all(&dev->read_queue);
		wake_up_interruptible_all(&dev->write_queue);
		if (debug)
			pr_debug("ringbuf_char: buffer cleared\n");
		break;

	case RINGBUF_CHAR_IOC_GET_STATS: {
		struct ringbuf_char_stats stats;

		mutex_lock(&dev->lock);
		ringbuf_char_fill_stats_locked(dev, &stats);
		mutex_unlock(&dev->lock);

		if (copy_to_user((void __user *)arg, &stats, sizeof(stats))) {
			ringbuf_char_note_failure(dev);
			return -EFAULT;
		}
		break;
	}

	case RINGBUF_CHAR_IOC_SET_CAPACITY: {
		u64 requested;

		if (copy_from_user(&requested, (const void __user *)arg,
				   sizeof(requested))) {
			ringbuf_char_note_failure(dev);
			return -EFAULT;
		}

		if (!ringbuf_char_capacity_valid_u64(requested)) {
			ringbuf_char_note_failure(dev);
			return -EINVAL;
		}

		mutex_lock(&dev->lock);
		ret = ringbuf_char_buffer_resize(&dev->buffer,
						(size_t)requested);
		if (ret == 0) {
			atomic64_inc(&dev->resizes);
			atomic64_inc(&dev->state_generation);
		}
		mutex_unlock(&dev->lock);

		if (ret) {
			ringbuf_char_note_failure(dev);
			return ret;
		}

		wake_up_interruptible_all(&dev->read_queue);
		wake_up_interruptible_all(&dev->write_queue);
		pr_info("ringbuf_char: resized buffer to %llu bytes\n",
			(unsigned long long)requested);
		break;
	}

	case RINGBUF_CHAR_IOC_GET_CAPACITY: {
		u64 capacity;

		mutex_lock(&dev->lock);
		capacity = dev->buffer.capacity;
		mutex_unlock(&dev->lock);

		if (copy_to_user((void __user *)arg, &capacity,
				 sizeof(capacity))) {
			ringbuf_char_note_failure(dev);
			return -EFAULT;
		}
		break;
	}

	case RINGBUF_CHAR_IOC_SET_MODE: {
		u32 mode;

		if (copy_from_user(&mode, (const void __user *)arg,
				   sizeof(mode))) {
			ringbuf_char_note_failure(dev);
			return -EFAULT;
		}

		if (mode & ~RINGBUF_CHAR_MODE_VALID_MASK) {
			ringbuf_char_note_failure(dev);
			return -EINVAL;
		}

		mutex_lock(&dev->lock);
		dev->mode = mode;
		atomic64_inc(&dev->state_generation);
		mutex_unlock(&dev->lock);
		wake_up_interruptible_all(&dev->read_queue);
		wake_up_interruptible_all(&dev->write_queue);
		pr_info("ringbuf_char: mode changed to 0x%x\n", mode);
		break;
	}

	case RINGBUF_CHAR_IOC_RESET_STATS:
		ringbuf_char_reset_stats(dev);
		break;

	default:
		ringbuf_char_note_failure(dev);
		return -ENOTTY;
	}

	return 0;
}

static __poll_t ringbuf_char_poll(struct file *file, poll_table *wait)
{
	struct ringbuf_char_dev *dev = file->private_data;
	__poll_t mask = 0;

	poll_wait(file, &dev->read_queue, wait);
	poll_wait(file, &dev->write_queue, wait);

	mutex_lock(&dev->lock);
	if (ringbuf_char_buffer_stored(&dev->buffer) > 0)
		mask |= POLLIN | POLLRDNORM;
	if (ringbuf_char_buffer_available(&dev->buffer) > 0)
		mask |= POLLOUT | POLLWRNORM;
	mutex_unlock(&dev->lock);

	return mask;
}

static const struct file_operations ringbuf_char_fops = {
	.owner = THIS_MODULE,
	.open = ringbuf_char_open,
	.release = ringbuf_char_release,
	.read = ringbuf_char_read,
	.write = ringbuf_char_write,
	.unlocked_ioctl = ringbuf_char_ioctl,
	.poll = ringbuf_char_poll,
	.llseek = no_llseek,
};

static int ringbuf_char_create_class(struct ringbuf_char_dev *dev)
{
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 4, 0)
	dev->class = class_create(RINGBUF_CHAR_CLASS_NAME);
#else
	dev->class = class_create(THIS_MODULE, RINGBUF_CHAR_CLASS_NAME);
#endif
	if (IS_ERR(dev->class))
		return PTR_ERR(dev->class);

	return 0;
}

static int __init ringbuf_char_init(void)
{
	struct ringbuf_char_dev *dev;
	int ret;

	if (!ringbuf_char_capacity_valid_u64(buffer_capacity)) {
		pr_err("ringbuf_char: invalid buffer_capacity=%u, expected %u..%u\n",
		       buffer_capacity, (unsigned int)RINGBUF_CHAR_MIN_CAPACITY,
		       (unsigned int)RINGBUF_CHAR_MAX_CAPACITY);
		return -EINVAL;
	}

	dev = kzalloc(sizeof(*dev), GFP_KERNEL);
	if (!dev)
		return -ENOMEM;

	mutex_init(&dev->lock);
	init_waitqueue_head(&dev->read_queue);
	init_waitqueue_head(&dev->write_queue);

	ret = ringbuf_char_buffer_init(&dev->buffer, buffer_capacity);
	if (ret) {
		pr_err("ringbuf_char: failed to allocate circular buffer: %d\n",
		       ret);
		goto err_free_dev;
	}

	ret = alloc_chrdev_region(&dev->devt, 0, 1, RINGBUF_CHAR_DEVICE_NAME);
	if (ret) {
		pr_err("ringbuf_char: alloc_chrdev_region failed: %d\n", ret);
		goto err_buffer_cleanup;
	}

	cdev_init(&dev->cdev, &ringbuf_char_fops);
	dev->cdev.owner = THIS_MODULE;
	ret = cdev_add(&dev->cdev, dev->devt, 1);
	if (ret) {
		pr_err("ringbuf_char: cdev_add failed: %d\n", ret);
		goto err_unregister_region;
	}

	ret = ringbuf_char_create_class(dev);
	if (ret) {
		pr_err("ringbuf_char: class_create failed: %d\n", ret);
		goto err_cdev_del;
	}

	dev->device = device_create(dev->class, NULL, dev->devt, NULL,
				    RINGBUF_CHAR_DEVICE_NAME);
	if (IS_ERR(dev->device)) {
		ret = PTR_ERR(dev->device);
		pr_err("ringbuf_char: device_create failed: %d\n", ret);
		goto err_class_destroy;
	}

	ringbuf_dev = dev;
	pr_info("ringbuf_char: loaded major=%u minor=%u capacity=%zu debug=%d\n",
		MAJOR(dev->devt), MINOR(dev->devt), dev->buffer.capacity,
		debug ? 1 : 0);

	return 0;

err_class_destroy:
	class_destroy(dev->class);
err_cdev_del:
	cdev_del(&dev->cdev);
err_unregister_region:
	unregister_chrdev_region(dev->devt, 1);
err_buffer_cleanup:
	ringbuf_char_buffer_cleanup(&dev->buffer);
err_free_dev:
	kfree(dev);
	return ret;
}

static void __exit ringbuf_char_exit(void)
{
	struct ringbuf_char_dev *dev = ringbuf_dev;

	if (!dev)
		return;

	mutex_lock(&dev->lock);
	dev->shutting_down = true;
	atomic64_inc(&dev->state_generation);
	mutex_unlock(&dev->lock);
	wake_up_interruptible_all(&dev->read_queue);
	wake_up_interruptible_all(&dev->write_queue);

	device_destroy(dev->class, dev->devt);
	class_destroy(dev->class);
	cdev_del(&dev->cdev);
	unregister_chrdev_region(dev->devt, 1);

	pr_info("ringbuf_char: unloaded bytes_read=%lld bytes_written=%lld opens=%lld ioctls=%lld failures=%lld\n",
		(long long)atomic64_read(&dev->total_bytes_read),
		(long long)atomic64_read(&dev->total_bytes_written),
		(long long)atomic64_read(&dev->open_calls),
		(long long)atomic64_read(&dev->ioctl_calls),
		(long long)atomic64_read(&dev->failed_operations));

	ringbuf_char_buffer_cleanup(&dev->buffer);
	kfree(dev);
	ringbuf_dev = NULL;
}

module_init(ringbuf_char_init);
module_exit(ringbuf_char_exit);

MODULE_AUTHOR("Shivam Singh");
MODULE_DESCRIPTION("Concurrent ring-buffer character device with ioctl control");
MODULE_LICENSE("GPL");
