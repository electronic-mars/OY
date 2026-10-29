pragma Singleton
import QtQuick

// The interface's words (i18n.py). `t` is the dictionary of the language in use, copied into
// the engine once per change of language: a binding over L.t reads plain JS, never Python.
QtObject {
    readonly property var t: i18n.t
    readonly property string lang: i18n.lang

    // forms "one|other" (English) or "one|few|many" (Ukrainian)
    function plural(n, forms) {
        var f = forms.split("|")
        if (f.length === 2)
            return f[n === 1 ? 0 : 1]
        var d = n % 10, h = n % 100
        return f[d === 1 && h !== 11 ? 0 : d >= 2 && d <= 4 && (h < 12 || h > 14) ? 1 : 2]
    }
    function num(x, digits) { return x.toFixed(digits).replace(".", t.dec) }
}
