"""MPRIS detail source (Tier 2): structured media metadata over D-Bus.

MPRIS is the freedesktop standard media-player interface: each player owns a bus name under
``org.mpris.MediaPlayer2.*`` and announces metadata + playback status via
``org.freedesktop.DBus.Properties.PropertiesChanged`` -- event-driven, no polling. VLC, mpv,
Elisa, Spotify and the browsers all export it.

Same shape as :mod:`kdence.browser`: a pure policy (:mod:`policy`, metadata -> label, no I/O), a
pure focus-gated tracker (:mod:`tracker`, latest player per app + TTL), and a thin hardware
source (:mod:`source`, ``dbus-fast``). Privacy: a ``file://`` track never stores its path (it
collapses to ``(local file)``), matching the caption/site generalisation. Opt-in, default OFF.
"""
