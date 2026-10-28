"""Manual smoke test: summarize a sample text into Kannada and print the result.

Uses whatever models/services your .env enables, so the first run may download
models or call Google Translate. For the hermetic unit tests run:
    python -m unittest -v test_app
"""
import sys

import backend


def main(language='kn'):
    text = (
        "Climate change is causing more frequent extreme weather events around the world. "
        "Heatwaves, floods and droughts are becoming longer and more intense. "
        "This affects agriculture, health, and infrastructure. "
        "Farmers face lower crop yields, while cities struggle with flooding and heat stress. "
        "Scientists say cutting greenhouse gas emissions quickly can limit the damage."
    )
    print(f"Summarizing into '{language}'...")
    result = backend.summarize(text, language=language, explain=True)
    print(f"\nMethod: {result.method}   Source language: {result.source_language}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    print('\n---SUMMARY---\n')
    print(result.summary)
    print('\n---KEYWORDS---\n')
    print(', '.join(result.keywords))


if __name__ == '__main__':
    main(*sys.argv[1:2])
