var pluginService = {
	appVersion: "0.0.0.0",
	baseUrl: "http://localhost/",
	REQUEST_PARAM: "request",
	SERVICE_PAGE: "PluginsService.aspx",
	timeOutAfterMs: 15000,
	
	ResponseState_Success: 0,
	ResponseState_Error: 1,
	
	getServiceUrl: function () {
		return pluginService.baseUrl + pluginService.SERVICE_PAGE;
	},
	
	call: function (command, arguments, onComplete) {
		var request = {
			Command: command,
			Arguments: arguments,
			AppVersion: pluginService.appVersion
		};
		
		var url = pluginService.getServiceUrl();
		var requestData = pluginService.REQUEST_PARAM + "=" + encodeURIComponent(JSON.stringify(request));
		
		$.ajax({
			type: "GET",
			crossDomain: true,
			dataType: "jsonp",
			data: requestData,
			contentType: "application/json; charset=utf-8",
			timeout: pluginService.timeOutAfterMs,
			url: url
		}).done(function(data, textStatus, jqXHR) {
			onComplete(data);
		}).fail(function(jqXHR, textStatus, errorThrown) {
			var data = {
				State: pluginService.ResponseState_Error,
				ErrorMessage: "Client Side Error",
				ErrorDetails: textStatus,
				ResponseData: null
			};
			
			onComplete(data);
		});
	}
}