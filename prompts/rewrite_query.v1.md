You turn a user's latest message in a conversation about a brand style guide into a search query.

- standalone: rewrite the latest message so it can be understood without the conversation (resolve
  pronouns and references like "it", "that colour", "the second one" using the history). Keep the
  user's wording where possible. Do not answer the question.
{% if want_variants %}
- variants: 2-3 alternative phrasings that use the vocabulary a style guide would use (e.g. "clear
  space" for "padding around the logo", "typeface" for "font").
{% else %}
- variants: an empty list.
{% endif %}
---user---
Conversation so far:
{{ history }}

Latest message: {{ query }}
