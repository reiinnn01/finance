(function () {
  var box = document.getElementById('estimate-box');
  if (!box) return;
  var type = document.getElementById('id_loan_type');
  var amount = document.getElementById('id_amount_requested');
  var term = document.getElementById('id_term_months');
  var timer = null;

  function money(value) {
    return 'PHP ' + Number(value).toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function update() {
    if (!type.value || !amount.value || !term.value) {
      box.hidden = true;
      return;
    }
    var url = box.dataset.url + '?loan_type=' + encodeURIComponent(type.value) + '&amount=' + encodeURIComponent(amount.value) + '&term=' + encodeURIComponent(term.value);
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) { box.hidden = true; return; }
        document.getElementById('est-interest').textContent = money(data.total_interest);
        document.getElementById('est-total').textContent = money(data.total_payable);
        document.getElementById('est-installment').textContent = money(data.installment);
        box.hidden = false;
      })
      .catch(function () { box.hidden = true; });
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(update, 300);
  }

  [type, amount, term].forEach(function (el) {
    el.addEventListener('input', schedule);
    el.addEventListener('change', schedule);
  });
  update();
})();
