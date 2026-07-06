var language = {
	currentLanguage: "en",
	currentLanguageContent: null,
	
	init: function (initialLanguage) {
		language.activeLanguage(initialLanguage);
	},
	
	activeLanguage: function (newActiveLanguage) {
		if (newActiveLanguage) {
			try {
				language.currentLanguageContent = eval("language_file_" + newActiveLanguage);
				language.currentLanguage = newActiveLanguage;
			} catch (ex) {
				language.currentLanguage = "en";
				language.currentLanguageContent = eval("language_file_" + language.currentLanguage);
			}
		}
		
		return language.currentLanguage;
	},
	
	get: function (text) {
		if (language.currentLanguageContent == null ||
			!language.currentLanguageContent.hasOwnProperty(text)) {
			return text;
		}
			
		return language.currentLanguageContent[text];
	},
	
	formatString: function (str) {
		for (i = 1; i < arguments.length; i++) {
			str = str.replace("{" + (i - 1) + "}", arguments[i]);
		}
		
		return str;
	},
	
	getFormat: function (text, args) {
		text = language.get(text);
		
		try {
			text = language.formatString(text, args);
		} catch (ex) { }
		
		return text;
	}
};
