document.addEventListener("click", (event) => {
  const confirmationControl = event.target.closest("[data-confirm-message]");
  if (
    confirmationControl
    && !window.confirm(confirmationControl.dataset.confirmMessage)
  ) {
    event.preventDefault();
    return;
  }

  const scrollControl = event.target.closest("[data-scroll-top]");
  if (scrollControl) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
});

// Show the USPS State dropdown when Country is USA, else the text box.
const locationKey = (value) => value.replace(/[.,]/g, "").trim().split(/\s+/).join(" ").toLowerCase();

for (const field of document.querySelectorAll("[data-us-state]")) {
  const country = field.closest("form")?.elements.namedItem("Country");
  if (!country) {
    continue;
  }
  const usCountries = field.dataset.usCountries.split("|");
  const select = field.querySelector("select");
  const input = field.querySelector("input");
  const sync = () => {
    const isUs = usCountries.includes(locationKey(country.value));
    const [active, inactive] = isUs ? [select, input] : [input, select];
    if (isUs && select.hidden) {
      // Carry typed text into the dropdown; a name it lacks leaves it blank.
      const value = locationKey(input.value);
      const option = [...select.options].find((choice) => !choice.hasAttribute("data-unmapped") && (
        locationKey(choice.value) === value || locationKey(choice.text.replace(/ \([A-Z]{2}\)$/, "")) === value
      ));
      select.value = option?.value ?? "";
    }
    active.hidden = active.disabled = false;
    inactive.hidden = inactive.disabled = true;
    active.id = field.dataset.fieldId;
    inactive.removeAttribute("id");
  };
  // The text box tracks dropdown choices, so switching back never restores a cleared State.
  select.addEventListener("change", () => {
    input.value = select.value;
  });
  country.addEventListener("input", sync);
}
