import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    property string label: ""
    property bool accent: false
    property string tooltip: ""
    signal clicked()

    implicitWidth: Math.max(64, content.width + 24)
    implicitHeight: 30
    radius: Colors.radius_control

    color: !root.enabled ? Colors.disabled_bg
         : mouse.containsMouse ? (accent ? Colors.primary_button_hover : Colors.secondary_hover)
         : mouse.pressed ? (accent ? Colors.primary_button : Colors.secondary)
         : accent ? Colors.primary_button : Colors.secondary

    opacity: root.enabled ? 1.0 : 0.55

    Text {
        id: content
        anchors.centerIn: parent
        text: root.label
        color: root.enabled ? (accent ? Colors.text_on_accent : Colors.text) : Colors.text_muted
        font.family: Colors.font_family
        font.pixelSize: Colors.font_size_ui
        font.bold: accent
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }

    Rectangle {
        visible: mouse.containsMouse && root.tooltip.length > 0
        z: 100
        width: tip.width + 12
        height: tip.height + 8
        radius: 4
        color: Colors.tooltip_bg
        anchors.bottom: parent.top
        anchors.bottomMargin: 4
        anchors.horizontalCenter: parent.horizontalCenter
        Text {
            id: tip
            anchors.centerIn: parent
            text: root.tooltip
            color: Colors.tooltip_fg
            font.family: Colors.font_family
            font.pixelSize: Colors.font_size_secondary
        }
    }
}
