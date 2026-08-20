import QtQuick
import QtQuick.Controls

Item {
    id: root
    property string statName: ""
    property string statColor: Colors.STAT_COLOR_FALLBACK
    property string statValue: ""
    property string statPct: ""
    property string statIcon: ""
    property int runeCount: 0
    property string costText: ""
    property bool negative: false
    height: 24

    readonly property int colIcon: 22
    readonly property int colName: 118
    readonly property int colValue: 36
    readonly property int colPct: 40
    readonly property int colRunes: 62
    readonly property int gap: 6

    Image {
        id: ico
        visible: root.statIcon.length > 0
        width: root.colIcon
        height: root.colIcon
        x: 0
        anchors.verticalCenter: parent.verticalCenter
        source: root.statIcon
        fillMode: Image.PreserveAspectFit
        smooth: true
        asynchronous: true
    }

    Rectangle {
        visible: root.statIcon.length === 0
        width: root.colIcon
        height: root.colIcon
        x: 0
        radius: 11
        color: root.statColor
        anchors.verticalCenter: parent.verticalCenter
        Text {
            anchors.centerIn: parent
            text: root.statName.length > 0 ? root.statName.charAt(0).toUpperCase() : "?"
            color: "#ffffff"
            font.family: Colors.font_family
            font.pixelSize: 11
            font.bold: true
        }
    }

    Text {
        x: root.colIcon + root.gap
        width: root.colName
        anchors.verticalCenter: parent.verticalCenter
        text: root.statName
        color: Colors.text
        font.family: Colors.font_family
        font.pixelSize: Colors.font_size_ui
        elide: Text.ElideRight
    }

    Text {
        x: root.colIcon + root.gap + root.colName + root.gap
        width: root.colValue
        anchors.verticalCenter: parent.verticalCenter
        text: root.statValue
        color: root.negative ? Colors.danger : Colors.text
        font.family: Colors.font_family
        font.pixelSize: Colors.font_size_ui
        font.bold: true
        horizontalAlignment: Text.AlignRight
    }

    Text {
        x: root.colIcon + root.gap + root.colName + root.gap + root.colValue + root.gap
        width: root.colPct
        visible: root.statPct.length > 0
        anchors.verticalCenter: parent.verticalCenter
        text: root.statPct
        color: {
            let p = parseFloat(root.statPct)
            if (p >= Colors.JET_GREEN) return Colors.success
            if (p >= Colors.JET_YELLOW) return Colors.warning
            return Colors.danger
        }
        font.family: Colors.font_family
        font.pixelSize: Colors.font_size_secondary
        horizontalAlignment: Text.AlignRight
    }

    Text {
        x: root.colIcon + root.gap + root.colName + root.gap + root.colValue + root.gap + root.colPct + root.gap
        width: root.colRunes
        visible: root.runeCount > 0
        anchors.verticalCenter: parent.verticalCenter
        text: root.runeCount + (root.runeCount > 1 ? " runes" : " rune")
        color: Colors.text_muted
        font.family: Colors.font_family
        font.pixelSize: Colors.font_size_secondary
        horizontalAlignment: Text.AlignRight
    }

    KamaAmount {
        x: root.colIcon + root.gap + root.colName + root.gap + root.colValue + root.gap + root.colPct + root.gap + root.colRunes + root.gap
        width: Math.max(24, root.width - x)
        visible: root.costText.length > 0
        amount: root.costText
        iconSize: 12
        pixelSize: Colors.font_size_secondary
        textColor: Colors.text_muted
        anchors.verticalCenter: parent.verticalCenter
    }
}
