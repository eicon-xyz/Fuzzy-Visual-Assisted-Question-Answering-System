# -*- coding: utf-8 -*-
"""
HAJIMI auto-operation assistant - safety control

Three-tier classification: green(allow) / yellow(warn) / red(block)
Keyword + semantic rules covering safe ops, file ops, system ops, network security.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SafetyResult:
    allowed: bool
    level: str  # "green" | "yellow" | "red"
    reason: str


# ============================================================================
# RED - high risk, force block
# ============================================================================

_RED_PATTERNS: list[tuple[re.Pattern, str]] = [
    # data destruction
    (
        re.compile(
            r"delete.{0,6}(all|every|entire).{0,4}(file|data|record|photo|video)", re.I
        ),
        "ban batch delete",
    ),
    (
        re.compile(r"(clear|clean).{0,6}(all|recycle.bin|desktop)", re.I),
        "ban clear all",
    ),
    (re.compile(r"(format)\s*[CcDd]:?"), "ban disk format"),
    (re.compile(r"rm\s+-rf|del\s+/[FS]/[QS]"), "ban dangerous command"),
    (
        re.compile(
            r"(permanently)?\s*delete.{0,4}(system.{0,2}file|driver|registry|boot\.ini)",
            re.I,
        ),
        "ban destroy system files",
    ),
    # account/password
    (
        re.compile(
            r"(crack|steal|get|extract).{0,8}(password|account|key|token|cookie|credential)",
            re.I,
        ),
        "ban steal credentials",
    ),
    (
        re.compile(
            r"(change|modify|reset|bypass).{0,4}(password|login|account).{0,4}(without|skip)",
            re.I,
        ),
        "ban bypass auth",
    ),
    (
        re.compile(r"(brute.force|credential.stuffing|password.dictionary)", re.I),
        "ban attack behavior",
    ),
    # payment/finance
    (
        re.compile(
            r"(auto|for.me|help.me).{0,6}(pay|payment|transfer|remit|top.up|order|purchase)",
            re.I,
        ),
        "ban auto payment",
    ),
    (
        re.compile(r"(fake.*review|paid.review|click.farm|review.fraud)", re.I),
        "ban fraud behavior",
    ),
    # cyber attacks
    (
        re.compile(r"(hack|intrusion|penetrate|attack|webshell|backdoor|phish)", re.I),
        "ban attack ops",
    ),
    (
        re.compile(r"(DDoS|port.scan|vulnerab.*test|SQL.inject)", re.I),
        "ban network attack",
    ),
    (re.compile(r"(virus|trojan|worm|ransomware)", re.I), "ban malware ops"),
    (
        re.compile(
            r"(mass.register|register.bot|vote.manip|fake.follower|traffic.fraud)", re.I
        ),
        "ban bot behavior",
    ),
    # privacy surveillance
    (
        re.compile(
            r"(monitor|surveil|eavesdrop|record).{0,4}(other|someone.else).{0,4}(screen|keyboard|input|chat)",
            re.I,
        ),
        "ban surveillance",
    ),
    (
        re.compile(
            r"(capture|record).{0,4}(other|someone.else).{0,4}(screen|chat|video.call)",
            re.I,
        ),
        "ban capture others screen",
    ),
    (
        re.compile(
            r"(read|peek|view).{0,4}(other|someone.else).{0,4}(chat.history|sms|email|message)",
            re.I,
        ),
        "ban privacy invasion",
    ),
    # system destruction
    (
        re.compile(
            r"(uninstall|delete|remove).{0,4}(operating.system|Windows|system.disk|System32)",
            re.I,
        ),
        "ban destroy OS",
    ),
    (
        re.compile(
            r"(turn.off|disable).{0,4}(firewall|antivirus|Windows\s?Defender)", re.I
        ),
        "ban disable security",
    ),
    (
        re.compile(
            r"(modify|tamper|overwrite).{0,4}(hosts|system.time|system.file)", re.I
        ),
        "ban tamper system",
    ),
    # illegal content
    (
        re.compile(r"(porn|gambl|drug.traffic|arms.traffic|money.launder|fraud)", re.I),
        "ban illegal content",
    ),
    (
        re.compile(
            r"(generate|make|forge).{0,4}(fake.id|fake.diploma|counterfeit)", re.I
        ),
        "ban forgery",
    ),
]

# ============================================================================
# YELLOW - medium risk, warn but allow
# ============================================================================

_YELLOW_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"(install|download|setup).{0,6}(software|app|application|program)", re.I
        ),
        "install software",
    ),
    (
        re.compile(
            r"(modify|change|config|adjust).{0,4}(system|display|network|power|account)",
            re.I,
        ),
        "modify system settings",
    ),
    (
        re.compile(r"(delete|remove|uninstall).{0,4}(file|program|app|software)", re.I),
        "delete operation",
    ),
    (
        re.compile(
            r"(download|save|save.as).{0,4}(file|image|video|music|document)", re.I
        ),
        "download file",
    ),
    (
        re.compile(r"(open|access|visit).{0,4}(web.page|website|link|URL)", re.I),
        "visit webpage",
    ),
    (
        re.compile(r"(registry|regedit|reg\s+add|reg\s+delete)", re.I),
        "registry operation",
    ),
    (
        re.compile(
            r"(cmd|command.prompt|powershell|terminal).{0,4}(admin|as.*run)", re.I
        ),
        "command line operation",
    ),
    (
        re.compile(r"(shutdown|restart|reboot|log.off|hibernate|sleep|lock)", re.I),
        "power operation",
    ),
    (
        re.compile(
            r"(compress|decompress|zip|pack).{0,4}(file|folder|directory)", re.I
        ),
        "file compression",
    ),
    (
        re.compile(
            r"(copy|move|cut).{0,4}(to.{0,4}(system.dir|Windows|Program.{0,4}Files|C:.Windows))",
            re.I,
        ),
        "system dir file op",
    ),
    (
        re.compile(r"(send|upload).{0,4}(to).{0,4}(email|cloud|server)", re.I),
        "upload file",
    ),
    (
        re.compile(r"(modify|edit).{0,4}(env.var|PATH|system.var)", re.I),
        "modify env vars",
    ),
]

# ============================================================================
# GREEN overrides - skip yellow false matches
# ============================================================================

_GREEN_OVERRIDES: list[re.Pattern] = [
    re.compile(
        r"(open|start|run|click).{0,12}(notepad|calc|mspaint|snipping|task.mgr|control.panel|explorer|file.explorer|browser|Chrome|Edge|Firefox|app|application)",
        re.I,
    ),
    re.compile(
        r"(view|show|display).{0,4}(desktop|folder|property|version|info|content)", re.I
    ),
    re.compile(r"(type|input|write|search|find|look.for)", re.I),
    re.compile(
        r"(press|click|select|switch|scroll|drag).{0,4}(button|menu|tab|window|icon|file)",
        re.I,
    ),
    re.compile(r"(adjust|change).{0,4}(volume|brightness|resolution|font|size)", re.I),
    re.compile(
        r"(create|make|new).{0,4}(folder|file|document|sheet|note|shortcut)", re.I
    ),
    re.compile(r"(rename)", re.I),
    re.compile(
        r"(check|test|verify|confirm).{0,4}(network|connection|status|whether)", re.I
    ),
    re.compile(
        r"(install|download|setup).{0,6}(to|on|in)\s+[Dd]", re.I
    ),  # "install X to D drive"
]


# ============================================================================
# Public API
# ============================================================================


def check_step(description: str) -> SafetyResult:
    """Check a single operation step."""
    if not description:
        return SafetyResult(allowed=True, level="green", reason="")

    desc = description.strip()

    # 1. green overrides first
    for pattern in _GREEN_OVERRIDES:
        if pattern.search(desc):
            return SafetyResult(allowed=True, level="green", reason="")

    # 2. check red
    for pattern, reason in _RED_PATTERNS:
        if pattern.search(desc):
            return SafetyResult(allowed=False, level="red", reason=reason)

    # 3. check yellow
    for pattern, reason in _YELLOW_PATTERNS:
        if pattern.search(desc):
            return SafetyResult(allowed=True, level="yellow", reason=reason)

    # 4. default green
    return SafetyResult(allowed=True, level="green", reason="")


def check_query(query: str) -> SafetyResult:
    """Check overall query (stricter: red blocks immediately)."""
    return check_step(query)
