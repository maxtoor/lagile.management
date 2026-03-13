document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("fieldset.collapse > h2, .inline-group.collapse > h2").forEach(function (heading) {
    var toggle = heading.querySelector(".collapse-toggle");
    if (!toggle) return;

    Array.prototype.slice.call(heading.childNodes).forEach(function (node) {
      if (node === toggle) return;
      if (node.nodeType !== Node.TEXT_NODE) return;
      var cleaned = (node.textContent || "").replace(/[()]/g, "").trim();
      if (cleaned) {
        node.textContent = cleaned + " ";
        return;
      }
      heading.removeChild(node);
    });

    toggle.textContent = "";
    toggle.setAttribute("aria-label", heading.textContent.trim() || "Apri sezione");
  });
});
