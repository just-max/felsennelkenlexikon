# Felsennelkenlexikon

Archiv des [Felsennelkenlexikons](https://web.archive.org/web/20161021102523/http://felsennelkenanger.de/lexikon/).

## Aufbau

Das Lexikon wurde am 21.10.2016 zum letzten Mal vom Internet Archiv archiviert. Aus dem archivierten HTML (im Repo unter `src/lexikon.html`) werden sämtliche Definitionen geparst und als Markdown Dateien ausgegeben (siehe hierzu `src/parser.py`). Diese werden vom Static-Site-Generator [Quartz](https://quartz.jzhao.xyz/) zu einer statischen Webseite gebündelt.

Standardmäßig soll bei Quartz der sämtliche Inhalt vom Repo übernommen werden. Um dies zu umgehen (und eine gewisse Flexibilität bei der Wahl des SSG zu lassen), werden lediglich Dateien die gegenüber dem Repo von Quartz geändert werden sollen, in diesem Repo verwaltet (unter `quartz/`).

## Bauen

Zum Bauen kann das Script `run.sh` verwendet werden:

- `./run.sh content_build`: parst das HTML und erstellt die Markdown Dateien, welche in `build/content/` abgelegt werden.
- `./run.sh container_build`: baut ein Container, standardmäßig mithilfe von Podman. Um stattdessen Docker zu verwenden, kann die `CONTAINER_CMD` Umgebungsvariable gesetzt werden: `CONTAINER_CMD=docker ./run.sh container_build`.
- `./run.sh container_run`: lässt den Container laufen (es gilt der gleiche Hinweis zu Docker). Dabei werden `build/content/` und `build/public` gemountet, wo Quartz nach Eingabedateien sucht bzw. sein Output schreibt. Die gebaute Seite kann z.B. mittels Caddy gehostet werden: `caddy run --config src/Caddyfile`.
- `./run.sh container_serve`: lässt den Container laufen, aber mountet nicht den Output-Ordner, sondern lässt Quartz sie über seinen eingebauten HTTP Server hosten.
- `./run.sh clean`: löscht den Ordner `build/`.
