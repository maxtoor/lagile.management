(function () {
  function enhanceMessages() {
    var messageLists = document.querySelectorAll('.messagelist');
    messageLists.forEach(function (list) {
      if (!(list instanceof HTMLElement)) {
        return;
      }
      if (list.dataset.toastBound !== '1') {
        list.dataset.toastBound = '1';
        list.classList.add('agile-message-stack');
      }
    });

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

      var isError = message.classList.contains('error') || message.classList.contains('errornote');
      if (!isError && message.dataset.autocloseBound !== '1') {
        message.dataset.autocloseBound = '1';
        window.setTimeout(function () {
          message.remove();
        }, 5000);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhanceMessages);
  } else {
    enhanceMessages();
  }
})();
