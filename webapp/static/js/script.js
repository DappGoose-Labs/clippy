document.addEventListener('DOMContentLoaded', (event) => {
    const sendButton = document.getElementById('sendButton');
    const userInput = document.getElementById('userInput');
    const chat = document.getElementById('chat');

    const sendMessage = () => {
        const userText = userInput.value;
        if (userText.trim() !== '') {
            const userMessage = document.createElement('div');
            userMessage.textContent = userText;
            userMessage.className = 'p-2 my-2 text-right bg-blue-900 rounded';
            chat.appendChild(userMessage);
            userInput.value = ''; // Clear input after sending
            const typingIndicator = document.createElement('div');
            typingIndicator.textContent = 'Typing...';
            typingIndicator.className = 'p-2 my-2 text-left bg-gray-700 rounded';
            chat.appendChild(typingIndicator);
            fetch('/send_message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: userText }),
            })
            .then(response => response.json())
            .then(data => {
                chat.removeChild(typingIndicator);
                const botMessage = document.createElement('div');
                botMessage.textContent = data.message;
                botMessage.className = 'p-2 my-2 text-left bg-green-900 rounded';
                chat.appendChild(botMessage);
                chat.appendChild(botMessage);
            })
            .catch((error) => {
                chat.removeChild(typingIndicator);
                console.error('Error:', error);
            });
        }
    };
    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
            e.preventDefault(); // Prevent the default action to stop form submission
        }
    });
});
