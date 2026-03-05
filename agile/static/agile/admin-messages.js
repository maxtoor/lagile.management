(function () {
  function enhanceMessages() {
    var messages = document.querySelectorAll('.messagelist li, .messagelist .success, .messagelist .warning, .messagelist .error, .messagelist .info, .messagelist .errornote');
    messages.forEach(function (message) {
      if (!(message instanceof HTMLElement)) {
        return;
      }
      if (message.dataset.dismissibleBound === '1') {
        return;
      }
      message.dataset.dismissibleBound = '1';
      message.classList.add('agile-dismissible-message');

      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'agile-message-close';
      button.setAttribute('aria-label', 'Chiudi messaggio');
      button.textContent = 'X';
      button.addEventListener('click', function () {
        message.remove();
      });

      message.appendChild(button);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhanceMessages);
  } else {
    enhanceMessages();
  }
})();
