(function () {
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var els = document.querySelectorAll(".reveal");
  if (reduce || !("IntersectionObserver" in window)) {
    els.forEach(function (e) { e.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    els.forEach(function (e, i) { e.style.transitionDelay = (i % 4) * 70 + "ms"; io.observe(e); });
  }

  // Count-up stats
  var nums = document.querySelectorAll("[data-count]");
  function run(el) {
    var end = +el.getAttribute("data-count"), t0 = null, dur = 1100;
    function step(t) {
      if (!t0) t0 = t;
      var p = Math.min((t - t0) / dur, 1);
      el.textContent = Math.round(end * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  if (!reduce && "IntersectionObserver" in window) {
    var co = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { run(en.target); co.unobserve(en.target); } });
    }, { threshold: 0.6 });
    nums.forEach(function (n) { co.observe(n); });
  }

  // Pulse calculator results when they change
  document.querySelectorAll(".result .big").forEach(function (b) {
    new MutationObserver(function () {
      b.classList.remove("bump"); void b.offsetWidth; b.classList.add("bump");
      setTimeout(function () { b.classList.remove("bump"); }, 200);
    }).observe(b, { childList: true, characterData: true, subtree: true });
  });
})();
