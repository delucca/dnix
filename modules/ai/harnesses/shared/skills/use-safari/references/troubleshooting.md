# Troubleshooting use-safari

## "Safari refuses scripts from Apple Events"

The Develop menu option is off. The user opens Safari Settings > Advanced, ticks "Show features for web developers", then enables Develop > "Allow JavaScript from Apple Events". Menu names follow Safari's language: in Portuguese they are Ajustes > Avançado > "Mostrar recursos para desenvolvedores web" and Desenvolvedor > "Permitir JavaScript de Eventos da Apple". Safari's own error text is localized too, so the script checks the `AllowJavaScriptFromAppleEvents` preference instead of matching the message.

## "macOS blocked Apple Events to Safari" (-1743)

The app running the shell (the terminal, editor or agent host) lacks Automation access to Safari. The user allows it under System Settings > Privacy & Security > Automation. If the prompt was dismissed and the app is not listed, `tccutil reset AppleEvents <bundle id of that app>` makes macOS ask again on the next call.

Every call failing with a connection or permission error that names neither setting usually means the shell runs inside a harness sandbox that blocks Apple Events. Run the command outside the sandbox.

## "Safari did not answer within 30s"

`do JavaScript` waits while the page shows a modal: an `alert`, a `confirm`, a print dialog or a sign-in sheet. Ask the user to look at Safari and dismiss it. Nothing reaches the page until they do.

## "no result: the code did not parse..."

Safari returns nothing for a script with a syntax error, so the wrapper cannot show the parser's message. Check the quoting first: wrap the JS in single quotes for the shell and use double quotes inside it. For more than one statement, pass a function, `'() => { ...; return value }'`, because a bare expression is wrapped in parentheses.

## Tab errors

- `N tabs match "x"`: the substring hit several tabs. Pass one of the listed `window:tab` ids.
- `no tab matches` / `no Safari window has id`: the tab moved or closed. Run `tabs` again.
- `Safari has no browser windows open` or `Safari is not running`: ask the user to open Safari. The script never launches it, so it cannot start a session the user did not expect.

## Clicks and forms

- A click that reports success but changes nothing usually hit a wrapper, not the control. Target the inner element with a narrower selector, or check what `--text` matched in the printed description.
- A control that reacts only to trusted (real) input events cannot be driven this way. Ask the user to click it.
- `fill` on a rich editor that ignores `textContent` changes needs the editor's own API through `evaluate`.

## Screenshots

- `screencapture failed`: the app running the shell needs Screen Recording permission (System Settings > Privacy & Security > Screen & System Audio Recording), and the window must not be minimized.
- Only the viewport is captured. For content below the fold, scroll with `evaluate 'window.scrollTo(0, 1200)'` and capture again.
- The capture makes the target tab current in its window, so the user sees that tab afterwards.
