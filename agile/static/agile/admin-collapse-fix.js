document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("fieldset.collapse > h2, .inline-group.collapse > h2").forEach(function (heading) {
    heading.childNodes.forEach(function (node) {
      if (node.nodeType !== Node.TEXT_NODE) return;
      if (!/[()]/.test(node.textContent || "")) return;
      node.textContent = (node.textContent || "").replace(/[()]/g, "");
    });
  });
});
