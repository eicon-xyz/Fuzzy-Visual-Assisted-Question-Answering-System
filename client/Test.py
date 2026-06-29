import pyttsx3

e = pyttsx3.init()
e.say("测试语音")
e.runAndWait()
print("播完了，从哪个设备听到的？")