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

// Turn a multi-select into an "Add" dropdown plus removable chips. The hidden
// select still holds the chosen values, so the form submits as before.
for (const select of document.querySelectorAll("select[multiple][data-chip-placeholder]")) {
  const picker = document.createElement("select");
  picker.className = "form-select";
  picker.id = select.id;
  select.removeAttribute("id");
  const chips = document.createElement("div");
  chips.className = "d-flex flex-wrap gap-2 mt-2";

  const render = () => {
    const options = [...select.options];
    picker.replaceChildren(
      new Option(select.dataset.chipPlaceholder, ""),
      ...options.filter((option) => !option.selected).map((option) => new Option(option.text, option.value)),
    );
    chips.replaceChildren(...options.filter((option) => option.selected).map((option) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "btn btn-sm btn-outline-secondary rounded-pill";
      chip.textContent = `${option.text} ×`;
      chip.setAttribute("aria-label", `Remove ${option.text}`);
      chip.addEventListener("click", () => {
        option.selected = false;
        render();
      });
      return chip;
    }));
  };

  picker.addEventListener("change", () => {
    const option = [...select.options].find((choice) => choice.value === picker.value);
    if (option) {
      option.selected = true;
    }
    render();
  });
  select.hidden = true;
  select.after(picker, chips);
  render();
}
