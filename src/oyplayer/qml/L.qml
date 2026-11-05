pragma Singleton
import QtQuick

// The interface's words (i18n.py). `t` is the dictionary of the language in use, copied into
// the engine once per change of language: a binding over L.t reads plain JS, never Python.
QtObject {
    readonly property var t: i18n.t
    readonly property string lang: i18n.lang
    readonly property bool rtl: i18n.rtl            // written right to left: the window mirrored
    readonly property string font: i18n.font        // the language's own font, or "" (Theme.uiFont)
    readonly property var plurals: i18n.plurals     // the form index of 0-199 (i18n.plural_table)

    // forms "one|other" (English), "one|few|many" (Ukrainian): as many as the language has
    function plural(n, forms) {
        var f = forms.split("|")
        return f[Math.min(plurals[n < 200 ? n : 100 + n % 100], f.length - 1)]
    }
    function num(x, digits) { return x.toFixed(digits).replace(".", t.dec) }
}
