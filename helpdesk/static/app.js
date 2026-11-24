'use strict';
document.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-editor], button[data-preview]');
  if (!button) return;
  const id = button.dataset.editor || button.dataset.preview;
  const field = document.getElementById(id);
  if (button.dataset.editor) {
    const a = field.selectionStart, b = field.selectionEnd;
    const selected = field.value.slice(a, b) || 'text';
    const formats = {bold: ['**','**'], italic: ['*','*'], list: ['\n- ','\n'], quote: ['\n> ','\n'], code: ['`','`']};
    const [start, end] = formats[button.dataset.format];
    field.setRangeText(start + selected + end, a, b, 'select');
    field.focus();
    return;
  }
  const preview = document.getElementById(id + '-preview');
  preview.hidden = false;
  preview.textContent = 'Loading preview…';
  button.disabled = true;
  try {
    const body = new URLSearchParams({body: field.value});
    const response = await fetch(button.dataset.url, {method: 'POST', credentials: 'same-origin',
      headers: {'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content}, body});
    if (!response.ok) throw new Error('Preview unavailable. Reload the page if your session expired.');
    const result = await response.json();
    preview.innerHTML = result.html; // Only server-sanitized Markdown output.
  } catch (error) { preview.textContent = error.message; }
  finally { button.disabled = false; }
});
