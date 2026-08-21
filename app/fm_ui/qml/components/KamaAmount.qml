import QtQuick

Row {
    id: root
    property string amount: ""
    property string suffix: ""
    property int iconSize: 14
    property color textColor: Colors.text
    property int pixelSize: Colors.font_size_ui
    property bool bold: false
    property bool icon: true
    property bool alignRight: false
    spacing: 4
    visible: root.amount.length > 0
    layoutDirection: root.alignRight ? Qt.RightToLeft : Qt.LeftToRight

    readonly property bool showIcon: root.icon && app.kamaIcon.length > 0 && root.amount.indexOf("(") < 0

    Text {
        text: root.amount
        color: root.textColor
        font.family: Colors.font_family
        font.pixelSize: root.pixelSize
        font.bold: root.bold
        anchors.verticalCenter: parent.verticalCenter
    }
    Image {
        visible: root.showIcon
        source: app.kamaIcon
        width: root.iconSize
        height: root.iconSize
        fillMode: Image.PreserveAspectFit
        smooth: true
        anchors.verticalCenter: parent.verticalCenter
    }
    Text {
        visible: root.suffix.length > 0
        text: root.suffix
        color: root.textColor
        font.family: Colors.font_family
        font.pixelSize: root.pixelSize
        font.bold: root.bold
        anchors.verticalCenter: parent.verticalCenter
    }
}
