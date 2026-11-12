(function () {
  function showError(message) {
    if (window.StatApi?.toast) {
      window.StatApi.toast(message);
      return;
    }
    alert(message);
  }

  window.LessonKit = window.LessonKit || {};
  window.LessonKit.showError = showError;
})();
