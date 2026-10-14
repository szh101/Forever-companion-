# Verification status

This public source snapshot contains companion 0.4.2 and addon 0.3.0. Installation
instructions are in the [English README](../README.md) and
[中文版 README](../README.zh-CN.md).

| Area | Current evidence |
| --- | --- |
| Windows Python / Lua contracts | 155 tests: 154 passed, 1 platform-dependent generic symlink test skipped; no failures or errors |
| Windows hidden GUI | Passed with synthetic snapshots, mocked clipboard and model access |
| Windows-specific path checks | Junction and hard-link rejection checks ran and passed |
| Recent shared UI changes on macOS | Pending macOS regression and native build validation for this snapshot |
| Real game capture and input handoff | Not verified by the above checks |
| Addon loading, export and native copy in the game client | Not verified by the above checks |
| Live provider requests and current account/model availability | Not verified by the above checks |

The Windows results cover the implementation carried into this snapshot. They
are not proof that a download has been installed on a reader's computer. Detailed
test scope is in [Windows verification](windows-verification.md).

Hidden checks do not touch the game, read real clipboard contents, send input or
make model requests. They cannot prove visual polish, foreground switching,
wheel behavior under a particular game mode, real captured pixels or addon API
permissions. Those checks must be recorded separately when actually performed.

The project has not received a Blizzard compliance certification. Avoiding game
automation and using public interfaces are implementation boundaries, not a
claim of official approval. Re-run relevant checks when the game client, model
provider, CLI, operating system or capture backend changes.

Local installation records, machine identifiers and private test receipts are
not part of the public documentation. Future release notes should identify the
public source revision and package checksums without including user data.
