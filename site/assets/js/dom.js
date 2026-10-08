// Builds page elements from data. Text always goes in as text, never as HTML, so values
// from an operator's feed cannot add markup or scripts to the page.

export function h(tag, attributes = {}, ...children) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === null || value === undefined || value === false) continue;
    if (name === "className") element.className = value;
    else if (name === "text") element.textContent = value;
    else if (name.startsWith("on") && typeof value === "function") {
      element.addEventListener(name.slice(2).toLowerCase(), value);
    } else element.setAttribute(name, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
}

// Only http and https links are made clickable; anything else is shown as text.
export function safeLink(url, text) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      return h("a", { href: parsed.href }, text ?? parsed.href);
    }
  } catch {
    // not a URL
  }
  return document.createTextNode(text ?? String(url));
}
