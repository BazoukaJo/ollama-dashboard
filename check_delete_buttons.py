import requests

response = requests.get('http://127.0.0.1:5000/')
content = response.text

print('Delete found:', 'Delete' in content)
print('fa-trash found:', 'fa-trash' in content)
print('btn-outline-danger found:', 'btn-outline-danger' in content)

# Check model card structure
start = content.find('mxbai-embed-large:latest')
if start != -1:
    # Find the end of this model card
    card_end = content.find('</div>', content.find('card-body', start) + 200)
    if card_end != -1:
        card_content = content[start:card_end]
        print('\nModel card content:')
        print(card_content)
        print('\n--- End of card ---')
else:
    print('Model not found in HTML')
