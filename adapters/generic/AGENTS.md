# Factory adapter for any harness (or a person)

Put `adapters/generic/bin` on PATH, then in a project:

    factory init --apply --preset generic --adapter generic     # then fill the <...> commands and models in factory.toml
    factory clock          # the 5-minute clock
    factory crew before-cut <row>   # before cutting a row
    factory dashboard      # build the page; publish it as an artifact if your harness can, else open the file
    factory retro          # end of day
    factory promote-lesson <id> --plugin-repo <checkout> [--push]

A role command in factory.toml gets its prompt on stdin, runs in the unit's work folder, and must pass {model}.
The reviewer writes its JSON form to $FACTORY_REVIEW_FORM; a crew agent to $FACTORY_CREW_OUTPUT. Declare
fresh_session = true on the reviewer when its command starts a fresh session. The factory rules for every session
are written into the project's AGENTS.md by init (a managed block from core/templates/factory-agents.md).
