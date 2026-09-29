(() => {
  const form = document.getElementById('chat-form');
  const status = document.getElementById('cost-estimate');
  if (!form || !status) return;

  const model = form.elements.model;
  const prompt = form.elements.prompt;
  const csrf = form.querySelector('[name="csrfmiddlewaretoken"]');
  let timer;
  let requestNumber = 0;
  let controller;

  function scheduleEstimate() {
    window.clearTimeout(timer);
    requestNumber += 1;
    const currentRequest = requestNumber;
    if (controller) controller.abort();

    if (!prompt.value.trim()) {
      status.className = 'cost-estimate';
      status.textContent = 'Enter a message to estimate its cost.';
      return;
    }

    status.className = 'cost-estimate';
    status.textContent = 'Updating estimated cost…';
    timer = window.setTimeout(async () => {
      controller = new AbortController();
      const body = new URLSearchParams({model: model.value, prompt: prompt.value});
      try {
        const response = await fetch(form.dataset.costEstimateUrl, {
          method: 'POST',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
            'X-CSRFToken': csrf.value,
          },
          body,
          credentials: 'same-origin',
          signal: controller.signal,
        });
        if (!response.ok) throw new Error('Estimate unavailable.');
        const result = await response.json();
        if (currentRequest !== requestNumber) return;

        status.textContent = `Estimated maximum cost: ${result.estimated_credits} credits ` +
          `(about ${result.estimated_input_tokens} input tokens plus up to ${result.output_token_allowance} output tokens).`;
        if (result.exceeds_balance) {
          status.classList.add('is-warning');
          status.textContent += ` This exceeds your current balance of ${result.balance} credits.`;
        }
      } catch (error) {
        if (error.name === 'AbortError' || currentRequest !== requestNumber) return;
        status.classList.add('is-error');
        status.textContent = 'Cost estimate unavailable; the server will check your balance before sending.';
      }
    }, 250);
  }

  prompt.addEventListener('input', scheduleEstimate);
  model.addEventListener('change', scheduleEstimate);
  scheduleEstimate();
})();
