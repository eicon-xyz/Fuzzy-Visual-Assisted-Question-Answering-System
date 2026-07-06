CKEDITOR.editorConfig = function( config ) {
	config.allowedContent = true;
	config.removePlugins = 'elementspath,magicline';
	config.extraPlugins = 'image2,openlink';
	config.openlink_modifier = 0;
	config.linkShowAdvancedTab = false;
  	config.linkShowTargetTab = false;
	config.skin = 'royal';
	config.width = '100%';
	config.height = 'calc(100vh - 90px)';
	config.toolbar = [
		{ items: [ 'Source', 'Find', '-', 'PasteText', 'PasteFromWord' ] },
		{ items: [ 'Bold', 'Italic', 'Underline', '-', 'Strike', 'Subscript', 'Superscript', '-', 'RemoveFormat' ] },
		{ items: [ 'TextColor', 'BGColor' ] },
		'/',
		{ items: [ 'NumberedList', 'BulletedList', '-', 'Outdent', 'Indent' ] },
		{ items: [ 'JustifyLeft', 'JustifyCenter', 'JustifyRight', 'JustifyBlock' ] },
		{ items: [ 'Link', 'Unlink', '-', 'Image', 'HorizontalRule' ] },
		'/',
		{ items: [ 'Format', 'Font', 'FontSize' ] }
	];
};

CKEDITOR.on('dialogDefinition', function( ev ) {
    var dialogName = ev.data.name,
    dialogDefinition = ev.data.definition;

    if (dialogName === 'image') {
        dialogDefinition.removeContents('advanced');
        dialogDefinition.removeContents('Link');
    }
});
