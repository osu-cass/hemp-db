(() => {
  // Waits before each automatic retry; the page gives up after the last one.
  const RETRY_DELAYS_MS = [5000, 10000, 15000, 30000];
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
    if (!state) {
      state = {
        destination: findOwned(loader, "[data-pending-items]"),
        sentinel: findOwned(loader, "[data-pending-sentinel]"),
        status: findOwned(loader, "[data-pending-status]"),
        keys: new Set(),
        nextUrl: loader.dataset.nextUrl,
        loading: false,
        loaded: false,
        failures: 0,
        retryTimer: null,
      };
      loaderStates.set(loader, state);
    }
    return state;
  }

  function canLoad(state) {
    return Boolean(state.nextUrl) && !state.loading && state.retryTimer === null
      && state.failures <= RETRY_DELAYS_MS.length;
  }

  // Re-observing makes the observer report the sentinel's current position,
  // so a short page that leaves it on screen still triggers the next load.
  function watch(state) {
    pageObserver.unobserve(state.sentinel);
    if (canLoad(state) && state.sentinel.offsetParent !== null) {
      pageObserver.observe(state.sentinel);
    }
  }

  function scheduleRetry(loader, state) {
    const delay = RETRY_DELAYS_MS[state.failures - 1];
    if (delay === undefined) {
      state.status.textContent = "Couldn't load more. Reload the page to try again.";
      return;
    }
    state.status.textContent = `Couldn't load. Retrying in ${delay / 1000} seconds...`;
    state.retryTimer = setTimeout(() => {
      state.retryTimer = null;
      loadPage(loader);
    }, delay);
  }

  async function loadPage(loader) {
    const state = getState(loader);
    if (!canLoad(state)) {
      return;
    }

    pageObserver.unobserve(state.sentinel);
    state.loading = true;
    state.status.textContent = loader.dataset.loadingMessage;
    loader.setAttribute("aria-busy", "true");

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
      const source = fragment
        .querySelector("template[data-pending-items]")
        ?.content.querySelector("[data-pending-fragment-items]");
      const page = fragment.querySelector("[data-pending-page]");
      if (!source || !page) {
        throw new Error("Pending changes response was not a fragment.");
      }

      // Rows can shift between pages while others review, so skip repeats.
      for (const item of Array.from(source.children)) {
        const key = item.dataset.pendingKey;
        if (key && !state.keys.has(key)) {
          state.destination.append(item);
          state.keys.add(key);
        }
      }

      state.nextUrl = page.dataset.nextUrl;
      state.loaded = true;
      state.failures = 0;
      state.status.textContent = state.destination.children.length === 0
        ? loader.dataset.emptyMessage
        : "";
    } catch (error) {
      state.failures += 1;
      console.error(error);
      scheduleRetry(loader, state);
    } finally {
      state.loading = false;
      loader.setAttribute("aria-busy", "false");
      watch(state);
    }
  }

  const pageObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        loadPage(entry.target.closest("[data-pending-loader]"));
      }
    }
  }, { rootMargin: "1000px 0px" });

  // Fetch while the open animation runs instead of after it.
  document.addEventListener("show.bs.collapse", (event) => {
    const loader = getCollapseLoader(event.target);
    if (loader && !getState(loader).loaded) {
      loadPage(loader);
    }
  });

  document.addEventListener("shown.bs.collapse", (event) => {
    const loader = getCollapseLoader(event.target);
    if (loader) {
      watch(getState(loader));
    }
  });

  document.addEventListener("hidden.bs.collapse", (event) => {
    const loader = getCollapseLoader(event.target);
    if (loader) {
      pageObserver.unobserve(getState(loader).sentinel);
    }
  });
})();
