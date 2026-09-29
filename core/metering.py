from .models import CatalogModel


def estimate_tokens(text):
    if not text:
        return 0
    return max(1, (len(text.encode('utf-8')) + 2) // 3)


def credits_for_usage(model, input_tokens, output_tokens):
    if (
        not isinstance(input_tokens, int)
        or isinstance(input_tokens, bool)
        or input_tokens < 0
        or not isinstance(output_tokens, int)
        or isinstance(output_tokens, bool)
        or output_tokens < 0
    ):
        raise ValueError('Token counts must be non-negative integers.')
    if not isinstance(model, CatalogModel):
        raise TypeError('A catalog model is required for metering.')

    total = (
        input_tokens * model.input_credits_per_1k_tokens
        + output_tokens * model.output_credits_per_1k_tokens
    )
    return (total + 999) // 1000


def estimate_request_cost(model, prompt, max_output_tokens):
    if not isinstance(max_output_tokens, int) or isinstance(max_output_tokens, bool) or max_output_tokens < 1:
        raise ValueError('The output-token allowance must be a positive integer.')

    input_tokens = estimate_tokens(prompt)
    return {
        'estimated_input_tokens': input_tokens,
        'output_token_allowance': max_output_tokens,
        'estimated_credits': credits_for_usage(model, input_tokens, max_output_tokens),
    }
