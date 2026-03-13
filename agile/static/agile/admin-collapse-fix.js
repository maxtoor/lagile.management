document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("fieldset.collapse > h2, .inline-group.collapse > h2").forEach(function (heading) {
    var toggle = heading.querySelector(".collapse-toggle");
    if (!toggle) return;
    var labelText = (heading.textContent || "")
      .replace(/\b(Mostra|Nascondi|Show|Hide)\b/gi, "")
      .replace(/[()]/g, "")
      .replace(/\s+/g, " ")
      .trim();
    var label = document.createElement("span");
    label.className = "agile-collapse-label";
    label.textContent = labelText;
    var cleanToggle = toggle.cloneNode(true);
    cleanToggle.textContent = "";

    heading.textContent = "";
    heading.appendChild(label);
    heading.appendChild(cleanToggle);

    cleanToggle.setAttribute("aria-label", labelText || "Apri sezione");
  });
});
