var utils = {
	getVersionAsInt: function (versionString) {
		return versionString.replace(/\./g, "0");
	},
	
	getParameter: function(name) {
	    var results = new RegExp('[\\?&]' + name + '=([^&#]*)').exec(window.location.href);
	    
	    if (!results) {
	        return null; 
	    }
	    
	    return results[1] || null;
	},

	isRetina: function() {
		return window.devicePixelRatio > 1;
	},

	stringEndsWith: function(str, suffix) {
	    return str.indexOf(suffix, str.length - suffix.length) !== -1;
	},

	formatPluginVersionForDisplay: function(version) {
		var idxOfStableVersionIndicator = version.lastIndexOf(".1000");

		if (idxOfStableVersionIndicator > 0) {
			version = version.substr(0, idxOfStableVersionIndicator);

			var idxOfLastZeroVersionIndicator = version.lastIndexOf(".0");

			if (idxOfLastZeroVersionIndicator > 0) {
				var potentialVersion = version.substr(0, idxOfLastZeroVersionIndicator);

				if (potentialVersion.length > 1) {
					version = potentialVersion;
				}
			}
		}

		return version;
	}
};