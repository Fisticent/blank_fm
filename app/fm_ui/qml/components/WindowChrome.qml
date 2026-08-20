import QtQuick
import QtQuick.Controls

// Barre de titre / chrome custom (fenêtre frameless, draggable).
Rectangle {
    id: root
    height: 38
    color: Colors.bg_card
    property string title: ""
    signal minimizeRequested()
    signal closeRequested()

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 4
        color: Colors.primary
    }

    Text {
        anchors.left: parent.left
        anchors.leftMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        text: root.title
        color: Colors.text
        font.family: Colors.font_family
        font.pixelSize: Colors.font_size_heading
        font.bold: true
    }

    // drag
    MouseArea {
        anchors.fill: parent
        property point start
        onPressed: (mouse) => start = Qt.point(mouse.x, mouse.y)
        onPositionChanged: (mouse) => {
            if (mouse.buttons & Qt.LeftButton) {
                let w = root.Window.window
                w.x += mouse.x - start.x
                w.y += mouse.y - start.y
            }
        }
        onDoubleClicked: (mouse) => root.Window.window.visibility = Window.Windowed
    }

    Row {
        anchors.right: parent.right
        anchors.rightMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        ThemedButton {
            id: minimizeBtn
            width: 34; height: 26
            label: "—"
            onClicked: root.minimizeRequested()
        }
        ThemedButton {
            id: closeBtn
            width: 34; height: 26
            label: "✕"
            accent: true
            onClicked: root.closeRequested()
        }
    }
}
