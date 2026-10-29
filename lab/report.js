"use strict";
const search = document.getElementById("search");
const outcome = document.getElementById("outcome");
const operations = Array.from(document.querySelectorAll("details.operation"));
function filterOperations() {
  const query = search.value.toLowerCase().trim();
  let count = 0;
  for (const operation of operations) {
    const matches = operation.dataset.search.includes(query) &&
      (outcome.value === "all" || outcome.value === operation.dataset.outcome);
    operation.hidden = !matches;
    if (matches) count++;
  }
  document.getElementById("visible-count").textContent = count + " of " + operations.length + " records";
  document.getElementById("empty").hidden = count !== 0;
}
search.addEventListener("input", filterOperations);
outcome.addEventListener("change", filterOperations);
function revealOperation() {
  const id = location.hash.slice(1);
  if (!/^operation-\d+$/.test(id)) return;
  const marker = document.getElementById(id);
  if (!marker) return;
  search.value = "";
  outcome.value = "all";
  filterOperations();
  const detail = marker.closest("details");
  detail.open = true;
  detail.querySelector("summary").focus();
  marker.scrollIntoView({block: "center"});
}
window.addEventListener("hashchange", revealOperation);
filterOperations();
revealOperation();
