# PSRTTY 1.11

2026-10-08  Ver1.11
・Reviewed UI, guides, descriptions and warnings; moved five-language text to separate JSON files in language.
・Japanese remains the initial language. Unreadable catalogues use English; missing or invalid entries individually use English.
・The executable includes complete English text. The selected language is preserved and restored at the next launch after files are repaired.
・File failures show one notice; details go to var/language.log. Distribution and updates include all five catalogues.

External catalogues: language/{ja,en,ru,zh,ko}.json, UTF-8, format 1.
Initial language remains Japanese. Language changes take effect after restart.
Unreadable files use English. Missing, empty or invalid entries individually use English.
Complete English fallback is embedded and generated from the same en.json.
The saved language is never replaced by fallback and recovers after file repair at the next launch.
File failures show one notice; detailed failures are recorded in var/language.log.
Distribution and update manifests include all five external files; 1.11+ packages missing them are rejected.
TX macros, RX/TX text, callsigns, radio identifiers and exported records remain untranslated.
Windows builds, fonts and real radio/audio operation require verification on the user's equipment.
