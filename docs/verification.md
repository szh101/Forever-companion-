# Verification status

This source snapshot contains companion 0.4.3 and addon 0.3.0. The records below
describe the previous 0.4.2 release; the English-interface release is awaiting its
own CI and package results. Installation
instructions are in the [English README](../README.md) and
[中文版 README](../README.zh-CN.md).

Windows release [v0.4.2-windows.5](https://github.com/szh101/Forever-companion-/releases/tag/v0.4.2-windows.5)
was built from `7cc94d9c895459968d7e021b103e2fea5cb239e4` in
[this passing workflow run](https://github.com/szh101/Forever-companion-/actions/runs/38528669848).
The setup executable, portable ZIP, AddOn ZIP and checksum file were subsequently
downloaded without authentication and their hashes verified.

| Area | Current evidence |
| --- | --- |
| Windows Python / Lua contracts | 156 tests: 155 passed, 1 platform-dependent generic symlink test skipped; no failures or errors |
| Windows hidden GUI | Passed with synthetic snapshots, mocked clipboard and model access |
| Windows-specific path checks | Long/8.3 path acceptance, junction and hard-link rejection checks passed |
| Packaged Windows application | Hidden executable self-test and native capture helper synthetic bitmap test passed; no capture session started |
| Windows installer | Nine synthetic checks passed, including fresh installation, exact bundled bytes, update backup, invalid paths, optional AddOn and uninstall preservation |
| Package privacy scan | No findings across 1,413 raw/decoded items and 11,980 code objects; compressed application archives decoded, installer scanned as a raw file |
| Public release downloads | All four assets downloaded anonymously; file sizes, ZIP integrity and SHA256 checksums matched |
| macOS Python / Lua contracts and native build | 156 tests: 150 passed, 6 Windows-specific skips; native capture helper compiled |
| macOS visible UI and capture | Not verified by CI |
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
