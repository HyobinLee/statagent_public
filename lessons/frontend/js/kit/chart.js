(function () {
  function resolveChartUrl(url) {
    return window.StatApi.chartUrl(url);
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.resolveChartUrl = resolveChartUrl;
})();
