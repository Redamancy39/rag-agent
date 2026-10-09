/** Python spans count Unicode code points, not JavaScript UTF-16 code units. */
export function adoptQuerySuggestion(
  question: string,
  previewOriginal: string,
  suggestion: {start: number; end: number; original: string; candidates: string[]},
  candidate: string
): string {
  if (question !== previewOriginal || !suggestion.candidates.includes(candidate)) return question
  const chars = Array.from(question)
  if (suggestion.start < 0 || suggestion.end > chars.length || suggestion.end <= suggestion.start) return question
  if (chars.slice(suggestion.start, suggestion.end).join('') !== suggestion.original) return question
  return [...chars.slice(0, suggestion.start), candidate, ...chars.slice(suggestion.end)].join('')
}
