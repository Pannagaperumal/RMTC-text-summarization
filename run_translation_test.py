from __future__ import print_function
import backend

def main():
    text = (
        "Climate change is causing more frequent extreme weather events around the world. "
        "This affects agriculture, health, and infrastructure."
    )
    print('Calling backend.funforfrontend for Kannada (kn)')
    summary, original, explanation, keywords = backend.funforfrontend(text, language='kn')
    print('\n---SUMMARY---\n')
    print(summary)
    print('\n---ORIGINAL---\n')
    print(original)

if __name__ == '__main__':
    main()
