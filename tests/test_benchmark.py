"""Measurement math and transport failure handling, without performance thresholds."""

from contextlib import redirect_stderr, redirect_stdout
import csv
import errno
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import socket

from lab.benchmark import Transport, aggregate, exchange, main, measure, percentile, summarize


class ShortTransport:
    def __init__(self):
        self.data = bytearray()

    def send(self, data):
        chunk = data[:2]
        self.data.extend(chunk)
        return len(chunk)

    def receive(self, count):
        chunk = bytes(self.data[:min(count, 3)])
        del self.data[:len(chunk)]
        return chunk


class BenchmarkTests(unittest.TestCase):
    def test_measurement_failure_preserved_after_cleanup_error(self):
        transport = Transport("pipe")
        closed = []

        def close(fd):
            closed.append(fd)
            if fd == 101:
                raise OSError("cleanup failure")

        original = RuntimeError("measured payload mismatch")
        with patch("lab.benchmark.os.pipe", return_value=(101, 102)), \
                patch("lab.benchmark.os.set_blocking"), \
                patch("lab.benchmark.os.close", side_effect=close):
            with self.assertRaisesRegex(RuntimeError, "measured payload mismatch") as caught:
                with transport:
                    raise original
        self.assertIs(caught.exception, original)
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertEqual(closed, [101, 102])
        self.assertEqual(transport.resources, [])

    def test_cleanup_attempts_every_endpoint_after_close_error(self):
        transport = Transport("pipe")
        closed = []
        def bad_close():
            closed.append("reader")
            raise OSError("reader close failed")
        transport.resources = [bad_close, lambda: closed.append("writer")]
        with self.assertRaisesRegex(OSError, "reader close failed"):
            transport.__exit__(None, None, None)
        self.assertEqual(closed, ["reader", "writer"])
        self.assertEqual(transport.resources, [])
        transport.__exit__(None, None, None)
        self.assertEqual(closed, ["reader", "writer"])

    def test_setup_failure_preserved_after_cleanup_error(self):
        transport = Transport("pipe")
        closed = []
        def close(fd):
            closed.append(fd)
            if fd == 101:
                raise OSError("cleanup failure")
        with patch("lab.benchmark.os.pipe", return_value=(101, 102)), \
                patch("lab.benchmark.os.set_blocking", side_effect=RuntimeError("setup failure")), \
                patch("lab.benchmark.os.close", side_effect=close):
            with self.assertRaisesRegex(RuntimeError, "setup failure") as caught:
                transport.__enter__()
        self.assertEqual(closed, [101, 102])
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertEqual(transport.resources, [])

    def test_nearest_rank_percentiles(self):
        values = list(range(1, 101))
        self.assertEqual([percentile(values, p) for p in [50, 95, 99]], [50, 95, 99])
        self.assertEqual(percentile([7], 99), 7)
        with self.assertRaises(ValueError):
            percentile([], 50)

    def test_throughput_counts_payload_once(self):
        result = summarize([100, 200], 1024 * 1024, 1_000_000_000, 500_000_000)
        self.assertEqual(result["logical_mib_s"], 2)
        self.assertEqual(result["round_trips_s"], 2)
        self.assertEqual(result["round_trip_ns"]["p99"], 200)

    def test_short_transfers_preserve_bytes(self):
        data, counters = exchange(ShortTransport(), b"abcdefgh")
        self.assertEqual(data, b"abcdefgh")
        self.assertEqual(counters, (4, 3, 3, 2))

    def test_zero_progress_and_eagain_abort(self):
        class Stalled(ShortTransport):
            def send(self, data):
                return 0
        with self.assertRaises(RuntimeError):
            exchange(Stalled(), b"abc")

        class Again(ShortTransport):
            def send(self, data):
                raise BlockingIOError(errno.EAGAIN, "fixture full")
        with self.assertRaises(BlockingIOError):
            exchange(Again(), b"abc")

    def test_corruption_is_not_a_performance_result(self):
        class Corrupt(ShortTransport):
            def receive(self, count):
                return b"x" * len(super().receive(count))
        with self.assertRaisesRegex(RuntimeError, "mismatch"):
            measure(Corrupt(), 8, 10, 0)

    def test_failed_repeats_are_not_zero_performance(self):
        runs = [{"backend": "pipe", "size": 64, "status": "inconclusive"},
                {"backend": "pipe", "size": 64, "status": "complete",
                 "measurement": {"logical_mib_s": 8, "round_trip_ns": {"p99": 90}}}]
        result = aggregate(runs)[0]
        self.assertEqual(result["completed_repeats"], 1)
        self.assertEqual(result["attempted_repeats"], 2)
        self.assertEqual(result["logical_mib_s_median"], 8)

    def test_actual_pipe_and_socketpair_integrity(self):
        for backend in ["pipe", "socketpair"]:
            with self.subTest(backend=backend), Transport(backend) as transport:
                measurement, samples = measure(transport, 64, 20, 5)
                self.assertEqual(len(samples), 20)
                self.assertEqual(measurement["iterations"], 20)
                self.assertGreater(measurement["wall_ns"], 0)

    def test_socket_setup_timeout_restores_process_default(self):
        previous = socket.getdefaulttimeout()
        with patch("lab.benchmark.socket.socketpair", side_effect=TimeoutError("fixture timeout")):
            with self.assertRaises(TimeoutError):
                with Transport("socketpair"):
                    self.fail("setup should fail")
        self.assertEqual(socket.getdefaulttimeout(), previous)

    def test_cli_saves_samples_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "benchmark"
            self.assertEqual(main(["--backends", "pipe", "--sizes", "64", "--iterations", "20",
                                   "--warmup", "3", "--repeats", "2", "--output", str(output)]), 0)
            with (output / "samples.csv").open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 40)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(len(manifest["job_order"]), 2)
            self.assertEqual(manifest["kind"], "round-trip-benchmark")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["--output", str(output)])

    def test_device_environment_failure_is_saved(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            output = Path(directory) / "missing-device"
            self.assertEqual(main(["--backends", "device", "--exclusive", "--sizes", "64",
                                   "--iterations", "2", "--repeats", "1", "--abi-program",
                                   str(Path(directory) / "not-present"), "--output", str(output)]), 2)
            run = json.loads((output / "run-000.json").read_text())
            self.assertEqual(run["status"], "inconclusive")
            self.assertNotIn("measurement", run)

    def test_rejects_invalid_bounds_and_unacknowledged_device(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
            for options in (["--sizes", "0"], ["--backends", "device"], ["--iterations", "0"],
                            ["--backends", "pipe", "pipe"]):
                with self.subTest(options=options), self.assertRaises(SystemExit):
                    main([*options, "--output", str(Path(directory) / "never-created")])


if __name__ == "__main__":
    unittest.main()
