import QtQuick

Item {
    id: root
    property string label: ""
    property string hint: ""
    default property alias content: rightSlot.data

    width: parent ? parent.width : 240
    implicitHeight: Math.max(28, labelCol.implicitHeight, rightSlot.height)
    height: implicitHeight

    Column {
        id: labelCol
        anchors.left: parent.left
        anchors.right: rightSlot.left
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Text {
            width: parent.width
            text: root.label
            color: Colors.text
            font.family: Colors.font_family
            font.pixelSize: Colors.font_size_ui
            wrapMode: Text.WordWrap
        }
        Text {
            visible: root.hint.length > 0
            width: parent.width
            text: root.hint
            color: Colors.text_muted
            font.family: Colors.font_family
            font.pixelSize: Colors.font_size_secondary
            wrapMode: Text.WordWrap
        }
    }

    Item {
        id: rightSlot
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: childrenRect.width
        height: Math.max(22, childrenRect.height)
    }
}
