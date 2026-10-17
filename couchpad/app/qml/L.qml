pragma Singleton
import QtQuick

// UI language. Russian strings are the keys; `en` comes from i18n.py.
QtObject {
    property string lang: "ru"
    property var en: ({})
    function t(s) { return lang === "en" ? (en[s] || s) : s }
}
