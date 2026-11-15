# Notification host appearance verification

Candidate `8b9d0392cfc27dfebd279af79b82e6aea8bab992` adds optional create and edit flags, preserves omitted values, returns the saved boolean, and rejects explicit changes on incompatible servers before a notification write.

Independent Gemini 4 Hydrogen High review passed with notes. The reviewer installed a retained wheel in a fresh Python 3.14 environment and passed 7 completion tests, 6 consumer contract tests, 11 feature and recovery tests, and direct console command checks against a loopback HTTP server. Bash and Zsh completion were exercised.

The retained artifact was built from `6db5c47483b83ce756b74ac5eafea7795b822ad8`. Its runtime, tests, contract and packaging inputs match the candidate. The candidate changes two documentation paragraphs, so the retained source distribution does not attest those final document bytes. The earlier full artifact gate passed 107 tests with one explicitly skipped real-account integration, two byte-identical builds and six negative controls.

Final-candidate artifact CI and separate actual server mutation and readback checks are pending. This record establishes no package publication or operating-system credential-backend acceptance.
