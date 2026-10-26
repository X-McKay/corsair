# Reviewing a command/argument injection claim

Use when the controlled value reaches a process spawn (titles such as "OS
command injection", descriptions naming a shell or an argument list). Apply the
standing rubric; this says what each rule checks for this class.

- R1 mechanism: the hypothesis must match how the cited `function` passes the
  value — concatenated into a shell string, or one element of an argument list —
  and the confinement the source does or omits.
- R2 differential: the control is an ordinary operand; the exploit differs only
  in `payload_parameter` and changes the process behavior through the exact call
  shape shown.
- R3 production logic: both run through the production spawn site with the
  recipe's fixed kwargs, not a mock subprocess.
- R4 disclosure, not echo: the claimed violation is disclosure of the protected
  value, not merely that a command ran or that supplied text was echoed.

Reject on the first contradicted rule; a real but unrelated injection elsewhere
still fails R1. You cannot assert execution occurred.
