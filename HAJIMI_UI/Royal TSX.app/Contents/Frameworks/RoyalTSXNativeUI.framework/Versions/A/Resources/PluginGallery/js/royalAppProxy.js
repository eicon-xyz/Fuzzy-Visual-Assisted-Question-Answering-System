// Proxy for Royal TSX Application

var royalAppProxy = {
	pluginServiceBaseUrl: "",
	featuresAllPluginsUrl: "",
	installedPluginInfosJson: "",

	isAvailable: function () {
 		try {
			if (window.webkit.messageHandlers.testScriptingInterface) {
				return true;
			}
		} catch (ex) { }

		return false;
	},
	
	getPluginServiceBaseUrl: function () {
		return royalAppProxy.pluginServiceBaseUrl;
	},

	getFeaturesAllPluginsUrl: function () {
		return royalAppProxy.featuresAllPluginsUrl;
	},

	getInstalledPluginInfos: function () {
		var pluginInfosJsonBase64 = royalAppProxy.installedPluginInfosJson;
		var pluginInfosJson = window.atob(pluginInfosJsonBase64);
		var pluginInfos = JSON.parse(pluginInfosJson);

		return pluginInfos;
	},
	
	showMessageBox: function (title, message, defaultButton) {
		if (!royalAppProxy.isAvailable()) {
			alert(title + "\r\n\r\n" + message);
		} else {
			var body = {
				"title": title,
				"message": message,
				"defaultButton": defaultButton
			};
			
			window.webkit.messageHandlers.requestShowMessageBox.postMessage(body);
		}
	},
	
	updatePlugins: function (pluginInfoArray) {
		if (!royalAppProxy.isAvailable()) {
			return;
		}
			
		var pluginsStr = JSON.stringify(pluginInfoArray);
		
		window.webkit.messageHandlers.requestUpdatePlugins.postMessage(pluginsStr);
	},
	
	installPlugins: function (pluginInfoArray, silent) {
		if (!royalAppProxy.isAvailable()) {
			return;
		}

		if (silent == null ||
			silent == undefined ||
			silent == "") {
			silent = false;
		}
		
		var pluginsStr = JSON.stringify(pluginInfoArray);

		var body = {
			"plugins": pluginsStr,
			"silent": silent
		};

		window.webkit.messageHandlers.requestInstallPlugins.postMessage(body);
	},
	
	uninstallPlugins: function (pluginInfoArray) {
		if (!royalAppProxy.isAvailable()) {
			return;
		}
			
		var pluginsStr = JSON.stringify(pluginInfoArray);

		window.webkit.messageHandlers.requestUninstallPlugins.postMessage(pluginsStr);
	},
	
	navigateTo: function (url) {
		location.href = url;
	}
};
