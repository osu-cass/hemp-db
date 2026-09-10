(() => {
  const loaderStates = new WeakMap();

  function findOwned(loader, selector) {
    return Array.from(loader.querySelectorAll(selector)).find(
      (element) => element.closest("[data-pending-loader]") === loader,
    );
  }

  function getCollapseLoader(collapse) {
    const body = Array.from(collapse.children).find((element) =>
      element.classList.contains("accordion-body"),
    );
    return body
      ? Array.from(body.children).find((element) =>
          element.matches("[data-pending-loader]"),
        )
      : null;
  }

  function getState(loader) {
    let state = loaderStates.get(loader);
    if (state) {
      return state;
    }

    const destination = findOwned(loader, "[data-pending-items]");
    state = {
      destination,
      keys: new Set(
        Array.from(destination.children, (item) => item.dataset.pendingKey).filter(Boolean),
      ),
      nextUrl: loader.dataset.nextUrl,
      loading: false,
      loaded: false,
      failed: false,
    };
    loaderStates.set(loader, state);
    return state;
  }

  function getButton(loader) {
    return findOwned(loader, "[data-pending-load]");
  }

  function setStatus(loader, message) {
    findOwned(loader, "[data-pending-status]").textContent = message;
  }

  function updateControls(loader, state) {
    const button = getButton(loader);
    button.disabled = state.loading;
    button.textContent = state.failed ? "Retry" : "Load more";
    button.hidden = state.loaded && !state.nextUrl && !state.failed;
    loader.setAttribute("aria-busy", state.loading ? "true" : "false");
  }

  function observeNextPage(loader, state) {
    const button = getButton(loader);
    if (
      pageObserver
      && state.nextUrl
      && !state.loading
      && !state.failed
      && !button.hidden
      && button.offsetParent !== null
    ) {
      pageObserver.observe(button);
    }
  }

  async function loadPage(loader) {
    const state = getState(loader);
    if (state.loading || !state.nextUrl) {
      return;
    }

    const button = getButton(loader);
    pageObserver?.unobserve(button);
    state.loading = true;
    state.failed = false;
    setStatus(loader, loader.dataset.loadingMessage);
    updateControls(loader, state);

    try {
      const response = await fetch(state.nextUrl, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok || response.redirected) {
        throw new Error(`Pending changes request failed: ${response.status}`);
      }

      const fragment = new DOMParser().parseFromString(
        await response.text(),
        "text/html",
      );
      const template = fragment.querySelector("template[data-pending-items]");
      const source = template?.content.querySelector(
        "[data-pending-fragment-items]",
      );
      const page = fragment.querySelector("[data-pending-page]");
      if (!source || !page) {
        throw new Error("Pending changes response was not a fragment.");
      }

      for (const item of Array.from(source.children)) {
        const key = item.dataset.pendingKey;
        if (!key || state.keys.has(key)) {
          continue;
        }
        state.destination.append(item);
        state.keys.add(key);
      }

      state.nextUrl = page.dataset.nextUrl;
      state.loaded = true;
      setStatus(
        loader,
        state.destination.children.length === 0 ? loader.dataset.emptyMessage : "",
      );
    } catch (error) {
      state.failed = true;
      setStatus(loader, "Unable to load this content. Try again.");
      console.error(error);
    } finally {
      state.loading = false;
      updateControls(loader, state);
      observeNextPage(loader, state);
    }
  }

  const pageObserver = "IntersectionObserver" in window
    ? new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const loader = entry.target.closest("[data-pending-loader]");
            loadPage(loader);
          }
        }
      }, { rootMargin: "200px 0px" })
    : null;

  document.addEventListener("shown.bs.collapse", (event) => {
    const loader = getCollapseLoader(event.target);
    if (!loader) {
      return;
    }

    const state = getState(loader);
    if (!state.loaded) {
      loadPage(loader);
      return;
    }
    observeNextPage(loader, state);
  });

  document.addEventListener("hidden.bs.collapse", (event) => {
    const loader = getCollapseLoader(event.target);
    if (loader) {
      pageObserver?.unobserve(getButton(loader));
    }
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-pending-load]");
    if (!button) {
      return;
    }
    loadPage(button.closest("[data-pending-loader]"));
  });
})();
