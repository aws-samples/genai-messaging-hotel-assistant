#!/usr/bin/env python3

import aws_cdk as cdk
from cdk.hotel_assistant import HotelAssistantStack


def main():
    app = cdk.App()
    HotelAssistantStack(app, 'HotelAssistant')
    app.synth()


if __name__ == '__main__':
    main()
