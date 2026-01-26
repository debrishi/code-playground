import { useState } from 'react';
import {
  Play,
  Moon,
  Sun,
  ChevronDown,
  Save,
  Maximize2,
  Minimize2,
  Terminal,
  AlertCircle,
  Clock,
  CheckCircle2
} from 'lucide-react';
import Editor from '@monaco-editor/react';

const LANGUAGES = ['C++', 'Java', 'Python', 'JavaScript'];

const DEFAULT_CODE = `#include <iostream>
using namespace std;

int main() {
    string name;
    // Type a name in the stdin box below!
    cin >> name;
    cout << "Hello " << name << "!" << endl;
    
    for(int i = 1; i <= 5; i++) {
        cout << "Count: " << i << endl;
    }
    
    return 0;
}`;

export default function App() {
  const [theme, setTheme] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const [code, setCode] = useState(DEFAULT_CODE);
  const [stdin, setStdin] = useState('Developer');
  const [output, setOutput] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [language, setLanguage] = useState('C++');
  const [stdinExpanded, setStdinExpanded] = useState(false);
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [isLangMenuOpen, setIsLangMenuOpen] = useState(false);

  // Toggle Theme
  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  // Mock Code Execution Logic
  const handleRunCode = () => {
    setIsRunning(true);
    setOutput(null);

    if (isFullScreen) {
      setIsFullScreen(false);
    }

    setTimeout(() => {
      let result = '';
      let status = 'Finished';
      let error = null;

      try {
        if (code.includes('while(true)') || code.includes('while(1)')) {
          status = 'Output Limit Exceeded';
          result = Array(1000).fill('1').join('');
        } else if (code.includes('throw') || code.includes('error')) {
          status = 'Compile Error';
          error = 'Line 14: error: expected ";" before "return"';
        } else {
          const lines = [];
          if (code.includes('cin >>')) {
            const inputVal = stdin.trim() || "World";
            if (code.includes('Hello')) {
              lines.push(`Hello ${inputVal}!`);
            }
          } else if (code.includes('Hello World')) {
            lines.push("Hello World!");
          }

          if (code.includes('for(int i')) {
            for (let i = 1; i <= 5; i++) {
              lines.push(`Count: ${i}`);
            }
          }

          if (lines.length === 0) {
            lines.push("Program finished with exit code 0");
          }

          result = lines.join('\n');
        }
      } catch (e) {
        status = 'Runtime Error';
        error = e.message;
      }

      setOutput({
        status,
        runtime: Math.floor(Math.random() * 10) + 1, // Random ms
        stdout: result,
        error: error
      });
      setIsRunning(false);
    }, 800);
  };

  const handleEditorChange = (value) => {
    setCode(value);
  };

  return (
    <div className={`min-h-screen font-sans ${theme === 'dark' ? 'bg-[#1e1e1e] text-gray-200' : 'bg-gray-50 text-gray-900'}`}>

      {/* --- Header --- */}
      <header className={`h-14 border-b flex items-center justify-between px-4 sticky top-0 z-20 ${theme === 'dark' ? 'bg-[#262626] border-[#333]' : 'bg-white border-gray-200'}`}>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <button
              onClick={handleRunCode}
              disabled={isRunning}
              className={`flex items-center space-x-2 px-4 py-2 rounded text-sm font-medium transition-all duration-300 transform active:scale-95 border outline-none focus:ring-2 focus:ring-opacity-50 focus:ring-green-400
                ${isRunning
                  ? theme === 'dark'
                    ? 'bg-[#333] text-gray-500 border-transparent cursor-not-allowed'
                    : 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
                  : theme === 'dark'
                    ? 'bg-[#132e21] text-green-400 border-[#1b4d30] hover:bg-[#1a3d2b] hover:border-[#23633e] hover:shadow-sm'
                    : 'bg-green-50 text-green-600 hover:bg-green-100 border-green-200 hover:shadow-sm'
                }`}
            >
              {isRunning ? <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" /> : <Play size={16} fill="currentColor" />}
              <span>Run Code</span>
            </button>
            <div className="relative">
              <button
                onClick={() => setIsLangMenuOpen(!isLangMenuOpen)}
                className={`flex items-center space-x-2 px-4 py-2 rounded text-sm border transition-all duration-300 active:scale-95 ${theme === 'dark' ? 'border-[#444] text-gray-300 hover:bg-[#333]' : 'border-gray-200 text-gray-600 hover:bg-gray-50'}`}
              >
                <span>{language}</span>
                <ChevronDown size={14} className={`transition-transform duration-200 ${isLangMenuOpen ? 'rotate-180' : ''}`} />
              </button>

              {isLangMenuOpen && (
                <>
                  {/* Backdrop to close when clicking outside */}
                  <div className="fixed inset-0 z-40" onClick={() => setIsLangMenuOpen(false)}></div>

                  {/* Dropdown Menu */}
                  <div className={`absolute top-full right-0 mt-1 w-40 rounded-md shadow-lg border overflow-hidden z-50 animate-in fade-in zoom-in-95 duration-200 
                        ${theme === 'dark' ? 'bg-[#1e1e1e] border-[#333] text-gray-300' : 'bg-white border-gray-200 text-gray-700'}`}
                  >
                    {LANGUAGES.map((lang) => (
                      <button
                        key={lang}
                        onClick={() => {
                          setLanguage(lang);
                          setIsLangMenuOpen(false);
                        }}
                        className={`w-full text-left px-4 py-2 text-sm transition-colors flex items-center justify-between
                                ${theme === 'dark' ? 'hover:bg-[#333]' : 'hover:bg-gray-50'}
                                ${language === lang ? (theme === 'dark' ? 'bg-[#262626] text-white' : 'bg-gray-50 text-black font-medium') : ''}
                            `}
                      >
                        <span>{lang}</span>
                        {language === lang && <CheckCircle2 size={14} className="opacity-70" />}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            className={`p-2.5 rounded transition-all duration-300 hover:scale-105 active:scale-95 ${theme === 'dark' ? 'bg-[#333] text-gray-400 hover:bg-[#404040]' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
            title="Save"
          >
            <Save size={18} />
          </button>

          <button
            className={`p-2.5 rounded transition-all duration-300 hover:scale-105 active:scale-95 ${theme === 'dark' ? 'bg-[#333] text-gray-400 hover:bg-[#404040]' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
            onClick={() => setIsFullScreen(!isFullScreen)}
            title={isFullScreen ? "Exit Full Screen" : "Full Screen"}
          >
            {isFullScreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
          </button>

          <button
            onClick={toggleTheme}
            className={`p-2.5 rounded transition-all duration-300 hover:scale-105 active:scale-95 ${theme === 'dark' ? 'bg-[#333] text-gray-400 hover:bg-[#404040]' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
            title={theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>

      {/* --- Main Content --- */}
      <main className="flex flex-col md:flex-row h-[calc(100vh-56px)] overflow-hidden">

        {/* Left Panel: Editor */}
        <section
          className={`flex flex-col relative flex-1 min-w-0 ${theme === 'dark' ? 'border-[#333]' : 'border-gray-200'}`}
        >
          <div className="flex-1 relative overflow-hidden">
            {/* Use InternalMonacoEditor for this preview, or <Editor> for local use */}
            <Editor
              height="100%"
              language={language.toLowerCase() === 'c++' ? 'cpp' : language.toLowerCase()}
              theme={theme === 'dark' ? 'vs-dark' : 'light'}
              value={code}
              onChange={handleEditorChange}
              loading={
                <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                  Loading Editor...
                </div>
              }
              options={{
                automaticLayout: true,
                minimap: { enabled: false },
                fontSize: 14,
                fontFamily: "'Menlo', 'Monaco', 'Courier New', monospace",
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                roundedSelection: false,
                readOnly: false,
                cursorStyle: 'line',
                renderLineHighlight: 'all',
                fixedOverflowWidgets: true,
                padding: { top: 0 },
                scrollbar: {
                  vertical: 'hidden',
                  horizontal: 'hidden'
                }
              }}
            />
          </div>

          {/* Editor Footer */}
          <div className={`h-8 border-t flex items-center justify-between px-4 text-xs select-none ${theme === 'dark' ? 'bg-[#1e1e1e] border-[#333] text-gray-400' : 'bg-white border-gray-100 text-gray-400'}`}>
            <div className="flex space-x-4">
              <span>Ln 5, Col 22</span>
              <span>Spaces: 4</span>
              <span>UTF-8</span>
            </div>
            <div>
              Read-only mode: Off
            </div>
          </div>
        </section>

        {/* Right Panel: Output & Input */}
        <section
          className={`flex flex-col border-l overflow-hidden
            ${theme === 'dark' ? 'bg-[#1e1e1e] border-[#333]' : 'bg-white border-gray-200'}
            ${isFullScreen ? 'w-0 opacity-0 border-none' : 'w-full md:w-[40%] opacity-100'}`}
        >

          {/* Output Header */}
          <div className={`flex items-center justify-between px-4 py-2 border-b ${theme === 'dark' ? 'border-[#333] bg-[#252526]' : 'border-gray-200 bg-gray-50'}`}>
            <div className="flex items-center space-x-2">
              <Terminal size={14} className="text-gray-500" />
              <span className={`text-sm font-medium ${theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}`}>Output</span>
            </div>
            <button
              onClick={() => setOutput(null)}
              className={`text-xs hover:text-gray-500 transition-colors duration-300 ${!output ? 'opacity-0 pointer-events-none' : 'opacity-100 text-gray-400'}`}
            >
              Clear
            </button>
          </div>

          {/* Output Content */}
          <div className={`flex-1 p-4 overflow-auto font-mono text-sm 
                scrollbar-thin 
                ${theme === 'dark'
              ? '[&::-webkit-scrollbar-track]:bg-[#1e1e1e] [&::-webkit-scrollbar-thumb]:bg-[#444] hover:[&::-webkit-scrollbar-thumb]:bg-[#555]'
              : '[&::-webkit-scrollbar-track]:bg-[#f1f1f1] [&::-webkit-scrollbar-thumb]:bg-[#ccc] hover:[&::-webkit-scrollbar-thumb]:bg-[#bbb]'
            }
                [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar]:w-2.5 [&::-webkit-scrollbar]:h-2.5`
          }>
            {isRunning ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-400 space-y-3 animate-pulse">
                <div className={`w-8 h-8 border-4 border-t-green-500 rounded-full animate-spin ${theme === 'dark' ? 'border-[#333]' : 'border-gray-200'}`}></div>
                <p>Running code...</p>
              </div>
            ) : output ? (
              <div className="space-y-4 animate-in slide-in-from-bottom-2 fade-in duration-500">
                {/* Status Badge */}
                <div className={`flex items-center space-x-2 ${output.status === 'Finished' ? 'text-green-500' :
                  output.status === 'Compile Error' ? 'text-red-500' : 'text-orange-500'
                  }`}>
                  {output.status === 'Finished' && <CheckCircle2 size={16} />}
                  {output.status === 'Compile Error' && <AlertCircle size={16} />}
                  {output.status === 'Output Limit Exceeded' && <AlertCircle size={16} />}
                  <span className="font-semibold">{output.status}</span>
                </div>

                {/* Runtime Info */}
                {output.status === 'Finished' && (
                  <div className="flex items-center space-x-2 text-xs text-gray-500">
                    <Clock size={12} />
                    <span>Finished in {output.runtime} ms</span>
                  </div>
                )}

                {/* Stdout / Error */}
                <div className={`p-3 rounded-md overflow-x-auto ${output.error
                  ? 'bg-red-50 text-red-700 border border-red-100'
                  : theme === 'dark' ? 'bg-[#2a2a2a] text-gray-300' : 'bg-gray-100 text-gray-800'
                  }`}>
                  <pre className="whitespace-pre-wrap">
                    {output.error || output.stdout}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-gray-400 opacity-70 transition-opacity duration-300 hover:opacity-100">
                <div className="flex flex-col items-center min-w-[200px]">
                  <Terminal size={48} strokeWidth={1} className={`mb-2 ${theme === 'dark' ? 'text-gray-600' : 'text-gray-300'}`} />
                  <p className="whitespace-nowrap font-medium">Run code to see output</p>
                </div>
              </div>
            )}
          </div>

          {/* Stdin Section */}
          <div className={`border-t flex flex-col ${theme === 'dark' ? 'border-[#333] bg-[#252526]' : 'border-gray-200 bg-gray-50'}`}>
            <div
              className="px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider flex items-center justify-between cursor-pointer hover:bg-opacity-80 transition-colors"
              onClick={() => setStdinExpanded(!stdinExpanded)}
            >
              <div className="flex items-center space-x-2">
                <span className={`text-gray-400 transform transition-transform duration-300 ${stdinExpanded ? 'rotate-0' : 'rotate-180'}`}>
                  <ChevronDown size={14} />
                </span>
                <span>stdin</span>
              </div>
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${theme === 'dark' ? 'bg-[#333] text-gray-400' : 'bg-gray-200 text-gray-600'}`}>Text</span>
            </div>
            <div
              className={`overflow-hidden ${stdinExpanded ? 'h-[35vh] opacity-100' : 'h-0 opacity-0'}`}
            >
              <div className={`p-2 h-full ${theme === 'dark' ? 'bg-[#1e1e1e]' : 'bg-white'}`}>
                <textarea
                  value={stdin}
                  onChange={(e) => setStdin(e.target.value)}
                  className={`w-full h-full p-3 text-sm font-mono resize-none focus:outline-none rounded border
                            ${theme === 'dark'
                      ? 'bg-[#1e1e1e] text-gray-300 border-[#333] focus:border-gray-500'
                      : 'bg-white text-gray-800 border-gray-200 focus:border-gray-300'
                    }`}
                  spellCheck="false"
                  placeholder="Enter input for stdin..."
                />
              </div>
            </div>
          </div>

        </section>
      </main>
    </div>
  );
}