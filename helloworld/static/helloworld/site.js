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
