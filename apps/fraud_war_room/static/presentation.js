(() => {
  "use strict";

  const slides = [...document.querySelectorAll("[data-slide]")];
  const dotNav = document.querySelector("#dotNav");
  const slideLabel = document.querySelector("#slideLabel");
  const progressBar = document.querySelector("#progressBar");
  let current = 0;
  let touchStartX = null;

  slides.forEach((slide, index) => {
    const dot = document.createElement("button");
    dot.className = "dot";
    dot.type = "button";
    dot.setAttribute("aria-label", `Go to slide ${index + 1}`);
    dot.addEventListener("click", () => show(index));
    dotNav.appendChild(dot);
  });

  function show(index) {
    current = (index + slides.length) % slides.length;
    slides.forEach((slide, slideIndex) => {
      slide.classList.toggle("is-active", slideIndex === current);
      slide.setAttribute("aria-hidden", slideIndex === current ? "false" : "true");
    });
    [...dotNav.children].forEach((dot, dotIndex) => {
      dot.classList.toggle("active", dotIndex === current);
      dot.setAttribute("aria-current", dotIndex === current ? "true" : "false");
    });
    slideLabel.textContent = `${String(current + 1).padStart(2, "0")} / ${String(slides.length).padStart(2, "0")}`;
    progressBar.style.width = `${((current + 1) / slides.length) * 100}%`;
    window.location.hash = `slide-${current + 1}`;
  }

  function next() { show(current + 1); }
  function previous() { show(current - 1); }

  document.querySelector("#nextButton").addEventListener("click", next);
  document.querySelector("#prevButton").addEventListener("click", previous);
  document.querySelectorAll("[data-next]").forEach((button) => button.addEventListener("click", next));
  document.querySelectorAll("[data-prev]").forEach((button) => button.addEventListener("click", previous));

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target.isContentEditable) return;
    if (["ArrowRight", "PageDown", " "].includes(event.key)) {
      event.preventDefault();
      next();
    } else if (["ArrowLeft", "PageUp"].includes(event.key)) {
      event.preventDefault();
      previous();
    } else if (event.key === "Home") {
      event.preventDefault();
      show(0);
    } else if (event.key === "End") {
      event.preventDefault();
      show(slides.length - 1);
    }
  });

  document.addEventListener("touchstart", (event) => {
    touchStartX = event.changedTouches[0]?.clientX ?? null;
  }, { passive: true });
  document.addEventListener("touchend", (event) => {
    if (touchStartX === null) return;
    const distance = event.changedTouches[0]?.clientX - touchStartX;
    if (Math.abs(distance) > 55) distance < 0 ? next() : previous();
    touchStartX = null;
  }, { passive: true });

  document.querySelector("#fullscreenButton").addEventListener("click", async () => {
    try {
      if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
      else await document.exitFullscreen();
    } catch (error) {
      console.warn("Fullscreen is unavailable in this browser.", error);
    }
  });

  const hashSlide = Number(window.location.hash.replace("#slide-", ""));
  show(Number.isInteger(hashSlide) && hashSlide > 0 ? hashSlide - 1 : 0);
})();
