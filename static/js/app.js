/* SSSys™ - Surplus Squad JavaScript */

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.alert-dismissible').forEach(function(alert) {
    setTimeout(function() {
      var bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      bsAlert.close();
    }, 5000);
  });
});
