"""Erzeugt die beiden Demo-Lehrbriefe und das Aufgabenblatt der Übungsarbeit neu. Nur nötig, wenn der Text unten geändert wird.

Aufruf: python demo/build_demo_pdfs.py   (benötigt das Paket reportlab)

Jede Liste unter PAGES ist genau eine PDF-Seite. Lernseiten, Fragen und die Übungsarbeit
der Demo verweisen auf diese Seitenzahlen; wer Seiten verschiebt, muss die Verweise anpassen.
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

FOLDER = Path(__file__).resolve().parent / 'study' / '10001 Lernen lernen (Demo)'
NOTE = 'Demo-Unterlage des Learning Hub. Für die Demo geschrieben; der Text darf frei verwendet und verändert werden.'

UNIT_1 = ('10001-01-S#1-demo.pdf', 'Lernen lernen · Kurseinheit 1', 'Abrufen und verteilt wiederholen', [
    [('h', 'Überblick'),
     ('p', 'Viele Lernende lesen ihre Unterlagen mehrfach und markieren wichtige Stellen. Das fühlt sich produktiv an, '
           'führt aber oft nur dazu, dass man den Stoff wiedererkennt. Diese Kurseinheit stellt zwei Techniken vor, '
           'deren Nutzen gut belegt ist: die Abrufübung und das verteilte Wiederholen.'),
     ('h', 'Lernziele'),
     ('b', 'Du kannst erklären, was Abrufübung ist und warum sie dem wiederholten Lesen langfristig überlegen ist.'),
     ('b', 'Du kannst die Vergessenskurve und den Verteilungseffekt beschreiben.'),
     ('b', 'Du kannst das Prinzip wachsender Wiederholungsabstände am Algorithmus SM-2 erläutern.')],
    [('h', '1 Abrufübung'),
     ('s', '1.1 Was Abrufübung bedeutet'),
     ('p', 'Bei der Abrufübung holst du Wissen aktiv aus dem Gedächtnis, ohne in die Unterlagen zu schauen: mit '
           'Karteikarten, mit Übungsfragen oder indem du ein Thema aus dem Kopf aufschreibst. Jeder erfolgreiche Abruf '
           'festigt die Erinnerung. Dieser Befund heißt Testeffekt.'),
     ('s', '1.2 Ein klassischer Befund'),
     ('p', 'Roediger und Karpicke (2006) ließen Studierende kurze Sachtexte lernen. Eine Gruppe las den Text mehrfach. '
           'Eine andere Gruppe las ihn einmal und gab ihn danach aus dem Gedächtnis wieder. Nach fünf Minuten erinnerte '
           'die Lesegruppe etwas mehr. Nach einer Woche erinnerte die Abrufgruppe deutlich mehr.'),
     ('s', '1.3 Die Flüssigkeitsillusion'),
     ('p', 'Wiederholtes Lesen macht einen Text vertraut. Vertrautheit wird leicht mit Können verwechselt. Wer sich '
           'selbst abfragt, merkt dagegen sofort, was noch fehlt. Abrufübung ist deshalb zugleich Lerntechnik und '
           'Selbstkontrolle.')],
    [('h', '2 Verteiltes Wiederholen'),
     ('s', '2.1 Die Vergessenskurve'),
     ('p', 'Hermann Ebbinghaus beschrieb 1885 anhand von Selbstversuchen mit sinnlosen Silben, dass frisch Gelerntes '
           'zuerst schnell und dann immer langsamer vergessen wird. Jede Wiederholung flacht diese Vergessenskurve ab.'),
     ('s', '2.2 Der Verteilungseffekt'),
     ('p', 'Dieselbe Lernzeit wirkt langfristig besser, wenn sie auf mehrere Sitzungen mit Abstand verteilt wird, statt '
           'sie am Stück zu verbringen. Massiertes Lernen kurz vor der Prüfung kann für den nächsten Tag reichen, hält '
           'aber schlecht.'),
     ('s', '2.3 Wachsende Abstände und SM-2'),
     ('p', 'Karteikartenprogramme planen Wiederholungen mit wachsenden Abständen. Der Algorithmus SM-2 von Piotr Woźniak '
           'sieht die erste Wiederholung nach einem Tag vor und die zweite nach sechs Tagen. Danach wird der Abstand '
           'jeweils mit einem Leichtigkeitsfaktor multipliziert, der von der eigenen Bewertung der Antwort abhängt. Nach '
           'einer falschen Antwort beginnt die Karte wieder mit kurzen Abständen. Auch der Learning Hub plant '
           'Wiederholungen nach diesem Prinzip.')],
    [('h', 'Zusammenfassung'),
     ('b', 'Abrufen festigt Wissen stärker als erneutes Lesen und zeigt zugleich, was noch fehlt.'),
     ('b', 'Vergessen verläuft anfangs schnell; Wiederholungen mit Abstand wirken dem entgegen.'),
     ('b', 'Wachsende Abstände halten den Aufwand klein: Sicheres wird selten, Unsicheres häufig wiederholt.'),
     ('h', 'Literatur'),
     ('p', 'Ebbinghaus, H. (1885). Über das Gedächtnis. Untersuchungen zur experimentellen Psychologie. Leipzig: Duncker &amp; Humblot.'),
     ('p', 'Roediger, H. L., &amp; Karpicke, J. D. (2006). Test-enhanced learning: Taking memory tests improves long-term '
           'retention. Psychological Science, 17(3), 249–255.'),
     ('p', 'Woźniak, P.: Beschreibung des Algorithmus SM-2 (SuperMemo 2).')],
])

UNIT_2 = ('10001-02-S#1-demo.pdf', 'Lernen lernen · Kurseinheit 2', 'Techniken auswählen und Lernen planen', [
    [('h', 'Überblick'),
     ('p', 'Kurseinheit 1 hat Abrufübung und verteiltes Wiederholen vorgestellt. Diese Kurseinheit ordnet weitere '
           'verbreitete Lerntechniken ein und zeigt, wie aus den Techniken ein Lernplan wird.'),
     ('h', 'Lernziele'),
     ('b', 'Du kannst verbreitete Lerntechniken nach ihrem belegten Nutzen einordnen.'),
     ('b', 'Du kannst verschachteltes Üben und Selbsterklärung beschreiben und anwenden.'),
     ('b', 'Du kannst einen Lernplan vom Prüfungstermin rückwärts aufstellen.')],
    [('h', '1 Welche Techniken sich lohnen'),
     ('s', '1.1 Eine Übersichtsarbeit'),
     ('p', 'Dunlosky und Kollegen (2013) bewerteten zehn verbreitete Lerntechniken anhand der Forschungslage. Als sehr '
           'nützlich stuften sie Abrufübung und verteiltes Üben ein. Als mäßig nützlich galten unter anderem '
           'verschachteltes Üben und Selbsterklärung. Markieren, wiederholtes Lesen und Zusammenfassen erhielten eine '
           'geringe Bewertung.'),
     ('s', '1.2 Verschachteltes Üben'),
     ('p', 'Beim verschachtelten Üben wechseln sich Aufgabentypen ab, statt jeden Typ im Block zu üben. Das ist '
           'anstrengender, weil man bei jeder Aufgabe erst erkennen muss, welches Verfahren passt. Genau diese '
           'Entscheidung wird in der Prüfung verlangt. In Studien mit Mathematikaufgaben schnitten verschachtelt Übende '
           'im späteren Test besser ab, obwohl sie während des Übens mehr Fehler machten (Rohrer und Taylor, 2007).'),
     ('s', '1.3 Selbsterklärung'),
     ('p', 'Bei der Selbsterklärung begründest du dir jeden Schritt: Warum gilt das? Wie hängt es mit dem zusammen, was '
           'ich schon weiß? Das deckt Lücken auf, die beim Lesen unbemerkt bleiben.')],
    [('h', '2 Einen Lernplan aufstellen'),
     ('s', '2.1 Vom Prüfungstermin rückwärts planen'),
     ('p', 'Trage zuerst feste Termine ein: Prüfung, Abgaben und Veranstaltungen. Verteile den Stoff dann rückwärts auf '
           'die verfügbaren Wochen. Halte die letzte Woche für Wiederholung und eine Probeklausur frei.'),
     ('s', '2.2 Konkrete Lernblöcke'),
     ('p', 'Ein Lernblock braucht ein prüfbares Ziel, zum Beispiel: Ich kann den Testeffekt an einem Beispiel erklären. '
           'Viele kommen mit Blöcken von 25 bis 50 Minuten und kurzen Pausen gut zurecht.'),
     ('s', '2.3 Wiederholungen einplanen'),
     ('p', 'Jeder Plan enthält neben neuem Stoff feste Zeiten für fällige Wiederholungen. Beginne eine Sitzung mit einer '
           'kurzen Abrufübung zum Stoff der letzten Sitzung. So verbindet der Plan beide Techniken aus Kurseinheit 1.')],
    [('h', 'Zusammenfassung'),
     ('b', 'Abrufübung und verteiltes Üben sind am besten belegt; Markieren und wiederholtes Lesen bringen wenig.'),
     ('b', 'Verschachteltes Üben trainiert die Wahl des passenden Verfahrens.'),
     ('b', 'Ein Lernplan beginnt bei den festen Terminen und enthält Zeiten für Wiederholungen.'),
     ('h', 'Literatur'),
     ('p', 'Dunlosky, J., Rawson, K. A., Marsh, E. J., Nathan, M. J., &amp; Willingham, D. T. (2013). Improving students\' '
           'learning with effective learning techniques. Psychological Science in the Public Interest, 14(1), 4–58.'),
     ('p', 'Rohrer, D., &amp; Taylor, K. (2007). The shuffling of mathematics problems improves learning. Instructional '
           'Science, 35, 481–498.')],
])

ASSIGNMENT = ('Einsendearbeiten/10001-uebungsarbeit-1-demo.pdf', 'Lernen lernen · Übungsarbeit 1', 'Übungsarbeit 1 (Demo)', [
    [('p', 'Entscheide zu jeder Aussage, ob sie zutrifft. Je Frage können mehrere Aussagen zutreffen.'),
     ('s', 'Frage 1: Abrufübung'),
     ('p', 'Welche Aussagen zur Abrufübung treffen zu?'),
     ('p', 'A) Abrufübung bedeutet, Wissen ohne Blick in die Unterlagen aus dem Gedächtnis zu holen.'),
     ('p', 'B) In der Studie von Roediger und Karpicke erinnerte nach einer Woche die Gruppe mehr, die den Text mehrfach gelesen hatte.'),
     ('p', 'C) Nach fünf Minuten erinnerte die Lesegruppe etwas mehr als die Abrufgruppe.'),
     ('p', 'D) Vertrautheit mit einem Text ist ein verlässliches Zeichen dafür, dass man ihn beherrscht.'),
     ('s', 'Frage 2: Verteiltes Wiederholen'),
     ('p', 'Welche Aussagen zum verteilten Wiederholen treffen zu?'),
     ('p', 'A) Nach der Vergessenskurve wird frisch Gelerntes zuerst langsam und dann immer schneller vergessen.'),
     ('p', 'B) Dieselbe Lernzeit wirkt langfristig besser, wenn sie auf mehrere Sitzungen mit Abstand verteilt wird.'),
     ('p', 'C) Der Algorithmus SM-2 sieht die zweite Wiederholung nach sechs Tagen vor.'),
     ('p', 'D) Nach einer falschen Antwort verlängert SM-2 den Abstand bis zur nächsten Wiederholung.'),
     ('s', 'Frage 3: Techniken und Lernplan'),
     ('p', 'Welche Aussagen zu Lerntechniken und Lernplanung treffen zu?'),
     ('p', 'A) Dunlosky und Kollegen stuften Markieren als sehr nützlich ein.'),
     ('p', 'B) Verschachtelt Übende machten während des Übens mehr Fehler, schnitten im späteren Test aber besser ab.'),
     ('p', 'C) Ein Lernplan wird vom Prüfungstermin rückwärts aufgestellt.'),
     ('p', 'D) Wiederholungen gehören nicht in den Lernplan, weil sie sich von selbst ergeben.')],
])


def build(name, series, title, pages):
    base = getSampleStyleSheet()
    styles = {
        'title': ParagraphStyle('title', parent=base['Title'], fontSize=20, leading=25, spaceAfter=2 * mm),
        'series': ParagraphStyle('series', parent=base['Normal'], fontSize=11, textColor='#555555', alignment=1),
        'note': ParagraphStyle('note', parent=base['Normal'], fontSize=9, textColor='#555555', alignment=1, spaceAfter=10 * mm),
        'h': ParagraphStyle('h', parent=base['Heading2'], fontSize=14, spaceBefore=6 * mm, spaceAfter=2 * mm),
        's': ParagraphStyle('s', parent=base['Heading3'], fontSize=11.5, spaceBefore=4 * mm, spaceAfter=1 * mm),
        'p': ParagraphStyle('p', parent=base['Normal'], fontSize=11, leading=16, spaceAfter=2 * mm),
    }
    styles['b'] = ParagraphStyle('b', parent=styles['p'], leftIndent=6 * mm, bulletIndent=1 * mm)
    (FOLDER / name).parent.mkdir(parents=True, exist_ok=True)
    story = [Paragraph(series, styles['series']), Paragraph(title, styles['title']), Paragraph(NOTE, styles['note'])]
    for number, page in enumerate(pages):
        if number:
            story.append(PageBreak())
        for kind, text in page:
            story.append(Paragraph(text, styles[kind], bulletText='•' if kind == 'b' else None))
        story.append(Spacer(1, 1))
    document = SimpleDocTemplate(str(FOLDER / name), pagesize=A4, leftMargin=25 * mm, rightMargin=25 * mm,
                                 topMargin=22 * mm, bottomMargin=22 * mm, title=f'{series}: {title}',
                                 author='Learning Hub Demo', invariant=1)

    def footer(canvas, doc):
        canvas.setFont('Helvetica', 9)
        canvas.setFillGray(0.4)
        canvas.drawCentredString(A4[0] / 2, 12 * mm, f'{series} · Seite {doc.page}')

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return FOLDER / name


if __name__ == '__main__':
    for unit in (UNIT_1, UNIT_2, ASSIGNMENT):
        print(build(*unit))
