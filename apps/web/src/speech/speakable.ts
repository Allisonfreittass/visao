// What a reply sounds like out loud: code, links and Markdown marks are for the screen.

const CODE_BLOCK = /```[\s\S]*?(```|$)/g;

export function speakableText(text: string): string {
  let spoken = text.replace(CODE_BLOCK, " Deixei o código na tela. ");
  spoken = spoken
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, "$1")
    .replace(/https?:\/\/\S+/g, "o link na tela")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/[ \t]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{2,}/g, "\n")
    .trim();
  // Two code blocks in a row would say it twice.
  return spoken.replace(/(Deixei o código na tela\.\s*)+/g, "Deixei o código na tela. ").trim();
}
