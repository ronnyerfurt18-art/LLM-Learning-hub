# Demo-Modul „Lernen lernen“

Ein kleines, vollständiges Modul zum Ausprobieren und als Vorlage für eigene Inhalte. Alle Texte wurden für die Demo geschrieben und dürfen frei verwendet und verändert werden.

Einrichten: `python3 tools/install_demo.py` oder `Demo.command` doppelklicken. Vorhandene Dateien werden nie überschrieben.

| Ordner | Inhalt | Ziel beim Einrichten |
|---|---|---|
| `study/10001 Lernen lernen (Demo)/` | Zwei Lehrbriefe (je vier Seiten) und das Aufgabenblatt der Übungsarbeit als PDF | Studienordner |
| `content/lernen-lernen-learning-pages.json` | Vier Lernseiten und ein Big Picture | `content/` |
| `content/assignments/lernen-lernen-uebung1.json` | Übungsarbeit mit drei Fragen zu je vier Aussagen | `content/assignments/` |
| `content/tutor/goals.json` | Drei Lernziele | wird in `content/tutor/goals.json` ergänzt |
| `imports/lernen_lernen_einheit1.json`, `…einheit2.json` | 14 Übungsfragen in sechs Aufgabentypen | `imports/` |
| `imports/seed.json` | Startliste der beiden Fragenpakete | wird in `imports/seed.json` ergänzt |

Die Fragen tragen `verified: false`, weil sie nicht von einem Menschen gegengeprüft sind.

Im Lernchat startet „Bereite mich auf Einsendearbeit 1 vor“ das Gespräch über die Übungsarbeit.

`build_demo_pdfs.py` erzeugt die drei PDFs neu (benötigt `reportlab`). Lernseiten, Fragen und Übungsarbeit verweisen auf die Seitenzahlen dieser PDFs.
